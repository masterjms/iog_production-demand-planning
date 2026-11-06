"""오늘 자재 주문 계산: 데이터·게시판 갱신 → 실제 재고 + 도착 예정(orders_pending.json) + 이번 주 확정 생산 + 다음 주 추정으로 MRP.
사용: python today.py 2026-11-04 [plans/R2602C_2026-11-01.json ...]"""
import sys, json, math, io, requests, pandas as pd, fetch_board
from planner import material_orders, forecast
from sim import load_demand
ROUND, START, END, TEAM = 'R2602C', '2026-11-01', '2026-12-04', 'DKU/26_DKU_GMG'
Z = {'P1': 0.6, 'P2': 0.4}
today = pd.Timestamp(sys.argv[1]); plans = sys.argv[2:] or ['plans/R2602C_2026-11-01.json']
for c in ['005930', 'BTC']:
    d = pd.read_excel(io.BytesIO(requests.get(f'http://play.ioground.kr:5005/plans_demand/demand_down/{c}').content), engine='xlrd')
    d['DATE'] = pd.to_datetime(d['DATE']); d = d.sort_values('DATE'); d.to_csv(f'data/demand_{c}.csv', index=False)
    print(c, d.tail(2).to_string(index=False, header=False).replace('\n', ' | '))
fetch_board.fetch(TEAM, ROUND, out='data_C')
m = pd.read_csv('data_C/material_0.csv'); print(m.to_string(index=False))
mat0 = {r['Material type']: int(r['Current level']) for _, r in m.iterrows()}
jobs = {}
for f in plans: jobs.update(json.load(open(f))['jobs'])
hist = load_demand('data'); hist = {k: {d: v for d, v in h.items() if d <= today} for k, h in hist.items()}
days = [today + pd.Timedelta(days=i) for i in range(14)]
fz = {k: forecast(hist[k], k, days, Z[k]) for k in ['P1', 'P2']}
from planner import allocate
entered = {d: jobs[str(d.date())] for d in days if str(d.date()) in jobs}
est = [d for d in days if str(d.date()) not in jobs]
plan = dict(entered)
L = pd.read_csv('data_C/ledger_0.csv')   # actual finished-goods stock after the last operated day
fg = {k: int(L[L.Action == f'SALES_INVENTORY_{k}'].sort_values('Date').iloc[-1]['Description'].split()[0]) for k in ['P1', 'P2']}
print('finished goods now:', fg)
for k in ['P1', 'P2']:   # days without an entered plan: same DP, carrying actual stock + remaining entered production - forecast demand
    carry = fg[k]
    for d in sorted(entered):
        if d >= today: carry = max(0, carry + entered[d][k] * 1000 - fz[k][d][0])
    if est:
        alloc, _ = allocate(k, est, {d: fz[k][d][1] for d in est}, carry // 1000)
        for d in est: plan.setdefault(d, {})[k] = alloc[d]
pending = [tuple(o) for o in json.load(open('orders_pending.json')) if pd.Timestamp(o[0]) >= today]   # [arrival, mat, qty, urgent]
print('pending arrivals:', pending)
orders, warns = material_orders(plan, mat0, pending, days, today - pd.Timedelta(days=1), START, END)
print(f'\n== orders (place TODAY {today.date()} marked *) ==')
for o in sorted(orders): print(('*' if o[0] == str(today.date()) else ' '), o)
print('warnings:', warns)
