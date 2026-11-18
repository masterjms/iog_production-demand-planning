"""오늘 자재 주문 계산: 데이터·게시판 갱신 → 실제 재고 + 도착 예정(orders_pending.json) + 이번 주 확정 생산 + 다음 주 추정으로 MRP.
사용: python today.py 2026-11-15   (plans/ 의 해당 라운드 주간계획을 전부 자동으로 읽음)"""
import sys, os, json, math, io, glob, requests, pandas as pd, fetch_board
from planner import material_orders, forecast, Z_DEFAULT
from sim import load_demand
ROUND, START, END, TEAM = 'R2602C', '2026-11-01', '2026-12-04', 'DKU/26_DKU_GMG'
Z = Z_DEFAULT   # P1 0.4 / P2 0.4 (planner와 동일)
today = pd.Timestamp(sys.argv[1]); plans = sys.argv[2:] or sorted(glob.glob(f'plans/{ROUND}_2*.json'))   # default: every weekly plan of the round
for c in ['005930', 'BTC']:
    d = pd.read_excel(io.BytesIO(requests.get(f'http://play.ioground.kr:5005/plans_demand/demand_down/{c}').content), engine='xlrd')
    d['DATE'] = pd.to_datetime(d['DATE']); d = d.sort_values('DATE'); d.to_csv(f'data/demand_{c}.csv', index=False)
    print(c, d.tail(2).to_string(index=False, header=False).replace('\n', ' | '))
fetch_board.fetch(TEAM, ROUND, out='data_C')
m = pd.read_csv('data_C/material_0.csv'); print(m.to_string(index=False))
mat0 = {r['Material type']: int(r['Current level']) for _, r in m.iterrows()}
jobs = {}
for f in plans: jobs.update(json.load(open(f))['jobs'])
ov = json.load(open('overrides.json')) if os.path.exists('overrides.json') else {}   # {"2026-11-27": {"P1": 180}} = production we cap on purpose through M1
for d, o in ov.items():
    if d in jobs:
        jobs[d] = {k: min(v, o.get(k, v)) for k, v in jobs[d].items()}; print('override (intended cap):', d, o)
hist = load_demand('data'); hist = {k: {d: v for d, v in h.items() if d <= today} for k, h in hist.items()}
days = [today + pd.Timedelta(days=i) for i in range(21)]   # look to the round end once it is within 3 weeks, never beyond it
days = [d for d in days if d <= pd.Timestamp(END)] if (pd.Timestamp(END) - today).days <= 20 else days[:14]
fz = {k: forecast(hist[k], k, days, Z[k]) for k in ['P1', 'P2']}
from planner import allocate
entered = {d: jobs[str(d.date())] for d in days if str(d.date()) in jobs}
est = [d for d in days if str(d.date()) not in jobs]
plan = dict(entered)
L = pd.read_csv('data_C/ledger_0.csv')   # actual finished-goods stock after the last operated day
fg = {k: int(L[L.Action == f'SALES_INVENTORY_{k}'].sort_values('Date').iloc[-1]['Description'].split()[0]) for k in ['P1', 'P2']}
last = pd.Timestamp(L.Date.max()); print('finished goods after', last.date(), ':', fg)   # ledger runs ~20:00; days after `last` are still to be sold
for k in ['P1', 'P2']:   # days without an entered plan: same DP, carrying actual stock + remaining entered production - forecast demand
    carry = fg[k]
    for d in pd.date_range(last + pd.Timedelta(days=1), days[-1]):   # every day the ledger has not processed yet (may start before `today`)
        if str(d.date()) in jobs:
            dem = fz[k][d][0] if d in fz[k] else hist[k].get(d, 0)   # day before `today`: known demand
            carry = max(0, carry + jobs[str(d.date())][k] * 1000 - dem)
    if est:
        alloc, _ = allocate(k, est, {d: fz[k][d][1] for d in est}, carry // 1000)
        for d in est: plan.setdefault(d, {})[k] = alloc[d]
if est: print('tentative jobs for days without an entered plan (DP estimate from carried stock, not on the board):')
for d in est: print('  ', d.date(), d.strftime('%a'), plan[d])
allp = [tuple(o) for o in json.load(open('orders_pending.json'))]   # [arrival, mat, qty, urgent]
BOM = {'P1': {'M1': 1, 'M2': 2}, 'P2': {'M3': 1, 'M2': 2}}
for d in pd.date_range(last + pd.Timedelta(days=1), today - pd.Timedelta(days=1)):   # days the ledger has not processed yet: roll the material stock forward
    for a, m_, q, u in allp:
        if pd.Timestamp(a) == d: mat0[m_] += q
    for p_, n_ in jobs.get(str(d.date()), {}).items():
        for m_, q in BOM[p_].items(): mat0[m_] -= q * n_ * 1000
if today - last > pd.Timedelta(days=1): print('material stock rolled forward to the start of', today.date(), ':', mat0)
pending = [o for o in allp if pd.Timestamp(o[0]) >= today]
print('pending arrivals:', pending)
orders, warns = material_orders(plan, mat0, pending, days, today - pd.Timedelta(days=1), START, END)
print(f'\n== orders (place TODAY {today.date()} marked *) ==')
for o in sorted(orders): print(('*' if o[0] == str(today.date()) else ' '), o)
print('warnings:', warns)
