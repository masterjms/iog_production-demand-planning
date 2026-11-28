"""Next-week production plans of the teams around us (public boards only).  python rivals_plan.py [first day] [last day]"""
import sys, io, datetime, requests, pandas as pd
from concurrent.futures import ThreadPoolExecutor
from team_compare import teams, BASE, RND
A, B = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ('2026-11-29', '2026-12-04')
TOP = ['26_DGU_KSH', '26_KGU_SCM9', '26_MJU_QCTeam', '26_DKU_HIDDEN', '26_SMART_FACTORY', '26_DKU_RM', '26_DKU_GMG', '26_DKU_HJD', '26_UOU_SMG', '26_DGU_LUCKY',
       '26_KGU_Team3', '26_KGU_SCM13', '26_KGU_SCM7', '26_MJU1', '26_DGU_YHW', '26_DKU_FIVE', '26_DKU_DNN', '26_DGU_KHJ']
U = {n: u for u, n in teams()}
def get(n):
    try: P = pd.read_html(io.StringIO(requests.get(f'{BASE}/plans_production/board/{U[n]}/{n}/{RND}', timeout=60).text))[0]
    except Exception as e: return n, None
    P = P[(P.Date >= A) & (P.Date <= B)]; P['j'] = pd.to_numeric(P['Planned #Jobs'], errors='coerce').fillna(0).astype(int)
    return n, P.pivot_table(index='Date', columns='Product', values='j', aggfunc='sum')
with ThreadPoolExecutor(8) as ex: R = dict(ex.map(get, TOP))
print(datetime.datetime.now().strftime('%H:%M'), f'plans {A}..{B}')
for n in TOP:
    W = R[n]
    if W is None or not len(W) or W.values.sum() == 0: print(f'{n:18s} -'); continue
    p1, p2 = W.get('P1', pd.Series(dtype=int)), W.get('P2', pd.Series(dtype=int))
    print(f'{n:18s} P1 {p1.tolist()} sum {int(p1.sum())} | P2 {p2.tolist()} sum {int(p2.sum())}')
