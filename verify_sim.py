"""sim.py 검증 기록: R2602A 9/13~9/18 공개 Ledger(팀 26_DKU_GMG)를 AUTO 운영 조건으로 재현해
날짜·항목별 금액을 대조한다.  실행: python verify_sim.py  -> verify_sim_R2602A.csv, 화면에 요약"""
import pandas as pd, fetch_board
from sim import simulate, load_demand

TEAM, ROUND = 'DKU/26_DKU_GMG', 'R2602A'
fetch_board.fetch(TEAM, ROUND, out='data_A')
act = pd.read_csv('data_A/ledger_0.csv')
for c in ['Revenue', 'Expense']:
    act[c] = act[c].astype(str).str.replace(r'[\$,]', '', regex=True).astype(int)
act = act[(act.Date <= '2026-09-18') & ((act.Revenue > 0) | (act.Expense > 0))]       # 금액이 있는 항목만 (JOB_CHANGE $0 제외)

dem = load_demand('data')
# 운영 당시 시스템이 쓴 P1 수요는 나중에 받은 다운로드 파일과 최대 1.4% 차이(사후 보정) -> Ledger의 판매+품절 합으로 역산한 값으로 고정
for d, v in {'2026-09-14': 249000, '2026-09-15': 248500, '2026-09-16': 253500, '2026-09-17': 256000, '2026-09-18': 260000}.items():
    dem['P1'][pd.Timestamp(d)] = v
days = pd.date_range('2026-09-13', '2026-09-18')
plan = {d: {'P1': (268 if d.weekday() < 5 else 0, None), 'P2': (78, None)} for d in days}   # AUTO 주간계획: P1 268 / P2 78 Job, SPT 순서
orders = [('2026-09-16', 'M1', 300000, False), ('2026-09-18', 'M3', 500000, False)]                                           # AUTO 재주문 도착분
sim, s = simulate(days, dem, plan, orders)
sim = sim[(sim.Revenue > 0) | (sim.Expense > 0)]

m = act.merge(sim, on=['Date', 'Action'], how='outer', suffixes=('_ledger', '_sim')).fillna(0)
m['match'] = (m.Revenue_ledger == m.Revenue_sim) & (m.Expense_ledger == m.Expense_sim)
m[['Date', 'Action', 'Revenue_ledger', 'Revenue_sim', 'Expense_ledger', 'Expense_sim', 'match']].sort_values(['Date', 'Action']).to_csv('verify_sim_R2602A.csv', index=False)
print(f'items compared: {len(m)}   matched: {int(m.match.sum())}   mismatched: {int((~m.match).sum())}')
print(f'ledger  revenue {act.Revenue.sum():,}  expense {act.Expense.sum():,}')
print(f'sim     revenue {s["revenue"]:,}  expense {s["expense"]:,}')
print(m.groupby('Action').size().to_string())
