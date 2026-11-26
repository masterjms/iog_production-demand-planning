"""Buffer for an M1/M3 order that is placed before the Saturday plan is fixed (no urgent purchase for M1/M3).
Simulates prices from the order day to Saturday (bootstrap of the last 60 log returns), the US-session shift of the
P1 level (N(0, US_SD)), the finished-goods carry-over from the locked plan, then runs the same forecast + DP the
Saturday planner runs, and compares the material the new plan needs with what will be on hand.
Use AFTER today.py for the same day (it refreshes data/ and data_C/):
  python buffer_mc.py 2026-11-19 M3 2026-11-30 [paths] [vol window, default 60]     # order day, material, next arrival of that material
Cost of being short s units = min(STOCKOUT*s, rescue order on Saturday (fee, arrives before the last day of the window));
cost of a spare unit = holding until the next arrival (the next order is reduced by it)."""
import sys, json, glob, numpy as np, pandas as pd
import planner
from planner import forecast, allocate, Z_DEFAULT, is_trading
from sim import load_demand, CFG
ROUND, END = 'R2602C', pd.Timestamp('2026-12-04')
US_SD, STOCKOUT = 0.02, 310
BOM = {'P1': {'M1': 1, 'M2': 2}, 'P2': {'M3': 1, 'M2': 2}}
today, mat, nxt_arr = pd.Timestamp(sys.argv[1]), sys.argv[2], pd.Timestamp(sys.argv[3])
N = int(sys.argv[4]) if len(sys.argv) > 4 else 400
WIN = int(sys.argv[5]) if len(sys.argv) > 5 else 60     # returns bootstrapped from the last WIN observations (20 = recent high volatility)
prod = 'P1' if mat == 'M1' else 'P2'
sat = today + pd.Timedelta(days=(5 - today.weekday()) % 7)
planner.US_SIGNAL = False                                   # the shift is simulated here
jobs = {}
for f in sorted(glob.glob(f'plans/{ROUND}_2*.json')): jobs.update(json.load(open(f))['jobs'])
hist = {k: {d: v for d, v in h.items() if d <= today} for k, h in load_demand('data').items()}[prod]
L = pd.read_csv('data_C/ledger_0.csv'); last = pd.Timestamp(L.Date.max())
fg0 = int(L[L.Action == f'SALES_INVENTORY_{prod}'].sort_values('Date').iloc[-1]['Description'].split()[0])
m0 = int(pd.read_csv('data_C/material_0.csv').set_index('Material type').loc[mat, 'Current level'])
arr = [tuple(o) for o in json.load(open('orders_pending.json')) if o[1] == mat]
week = [sat + pd.Timedelta(days=i) for i in range(1, 8)]; look = [week[-1] + pd.Timedelta(days=i) for i in range(1, 3)]
week = [d for d in week if d <= END]                         # last week: no production after the round ends
v = np.array([hist[d] for d in sorted(hist)][-(WIN + 1):], float); rets = np.diff(np.log(v[v > 0])); rets = rets - rets.mean()
for d in pd.date_range(max(hist) + pd.Timedelta(days=1), today):   # preview run for a later day: prices up to that day assumed unchanged
    if prod == 'P2' or is_trading(d): hist[d] = hist[max(hist)]
fut = [d for d in pd.date_range(today + pd.Timedelta(days=1), sat) if prod == 'P2' or is_trading(d)]
stock = m0                                                  # material on hand at the end of Saturday, before this order
for d in pd.date_range(last + pd.Timedelta(days=1), sat):
    stock += sum(q for a, _, q, _ in arr if pd.Timestamp(a) == d) - BOM[prod][mat] * jobs.get(str(d.date()), {}).get(prod, 0) * 1000
win = [d for d in week if d < nxt_arr]                      # production days this order has to cover


def need(h, mu):
    carry = fg0
    for d in pd.date_range(last + pd.Timedelta(days=1), sat):
        carry = max(0, carry + jobs.get(str(d.date()), {}).get(prod, 0) * 1000 - h.get(d, 0))
    hs = dict(h); k = max(hs); hs[k] = int(round(hs[k] * np.exp(mu)))
    fc = forecast(hs, prod, week + look, Z_DEFAULT[prod])
    a, _ = allocate(prod, week, {d: fc[d][1] for d in week}, carry // 1000, {d: fc[d][1] for d in look}, END)
    return sum(a[d] for d in win) * 1000 - stock - sum(q for a_, _, q, _ in arr if sat < pd.Timestamp(a_) < nxt_arr)


base = need({**hist, **{d: hist[max(hist)] for d in fut}}, 0.0)
rng = np.random.default_rng(1); x = []
for _ in range(N):
    h = dict(hist); p = hist[max(hist)]
    for d in fut:
        p = p * np.exp(rng.choice(rets)); h[d] = int(round(p))
    x.append(need(h, rng.normal(0, US_SD) if prod == 'P1' else 0.0) - base)
x = np.array(x)
fee = CFG['mat_order'][mat]; hold = CFG['mat_hold'][mat] * (nxt_arr - (today + pd.Timedelta(days=CFG['mat_lt'][mat]))).days
print(f'{mat} ordered {today.date()}: need now {base:,} (window {win[0].date()}..{win[-1].date()}, {len(fut)} price days still open, {N} paths)')
print('change of the need by Saturday: sd %.0fK, pct 5/25/50/75/90/95/99 = %s K' % (x.std() / 1e3, np.round(np.percentile(x, [5, 25, 50, 75, 90, 95, 99]) / 1e3).astype(int).tolist()))
print('buffer   P(short)  exp.short  loss no rescue   loss with Sat rescue   (incl. holding of spare units, $M)')
best = None
for B in range(0, 121000, 10000):
    s = np.maximum(x - B, 0); sp = np.maximum(B - x, 0) * hold
    c0, c1 = (STOCKOUT * s + sp).mean() / 1e6, (np.minimum(STOCKOUT * s, fee) + sp).mean() / 1e6
    print(f'{B/1e3:5.0f}K   {100*(s > 0).mean():5.1f}%   {s.mean()/1e3:6.1f}K   {c0:10.2f}   {c1:14.2f}')
    if best is None or c1 < best[1]: best = (B, c1)
print(f'-> buffer {best[0]/1e3:.0f}K (order {base + best[0]:,})')
