"""Fast look before the Saturday lock: fetch every team's production board, then our final rank for flat Samsung scenarios and
a small Monte Carlo, for the plan on the board (ON) and the alternative (OFF).   python quick_rank.py"""
import sys, io, datetime, requests, pandas as pd, numpy as np
from concurrent.futures import ThreadPoolExecutor
from team_compare import teams, BASE, RND, OUT
def get(t):
    u, n = t
    try: pd.read_html(io.StringIO(requests.get(f'{BASE}/plans_production/board/{u}/{n}/{RND}', timeout=40).text))[0].to_csv(f'{OUT}/{n}_production0.csv', index=False)
    except Exception: pass
with ThreadPoolExecutor(16) as ex: list(ex.map(get, teams()))
sys.argv = ['rank_mc.py', '1500']; import rank_mc as M
ME = M.ME; OFF = {'2026-11-30': 174, '2026-12-01': 182, '2026-12-02': 182, '2026-12-03': 182, '2026-12-04': 182}
ent = 0; lev = []
for t in M.D.columns:
    P = pd.read_csv(f'{OUT}/{t}_production0.csv'); P = P[(P.Date >= '2026-12-01') & (P.Date <= '2026-12-04') & (P.Product == 'P1')]
    v = pd.to_numeric(P['Planned #Jobs'], errors='coerce').fillna(0)
    if v.sum() > 0: ent += 1; lev.append(v.mean())
print(datetime.datetime.now().strftime('%H:%M:%S'), f'teams with a plan: {ent}/71, Tue-Fri P1 per day median {np.median(lev):.0f}')
print('Samsung week   ON: rank (gap to 10th)   OFF: rank (gap to 10th)')
for f in (-0.08, -0.05, -0.02, 0.0, 0.02, 0.05, 0.08):
    out = []
    for kw in (dict(), dict(mine=OFF, cap=176, mx=182)):
        r, _, F = M.run(0.0, 0.5, flat=f, **kw); v = F.iloc[0].sort_values(ascending=False); out.append(f'{int(r[0]):2d} ({(v[ME] - v.iloc[9]) / 1e6:+5.1f}M)')
    print(f'   {f*100:+3.0f}%          {out[0]}            {out[1]}')
for nm, kw in (('ON ', dict()), ('OFF', dict(mine=OFF, cap=176, mx=182))):
    M.rng = np.random.default_rng(3); r, wk, F = M.run(0.0, 0.5, **kw)
    print(f'MC {nm}: P(top10) {100*(r<=10).mean():.0f}%  median rank {np.median(r):.0f} | Samsung down>2%: {100*(r[wk<-0.02]<=10).mean():.0f}%  flat: {100*(r[abs(wk)<=0.02]<=10).mean():.0f}%  up>2%: {100*(r[wk>0.02]<=10).mean():.0f}%')
v = F.median().sort_values(ascending=False); print('median final balance:', ', '.join(f'{t[3:]} {x/1e6:.0f}' for t, x in v.head(13).items()))
