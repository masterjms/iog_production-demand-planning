"""Re-optimise the sequences of past production days with fastshop and compare with what was on the boards.
Writes seq_backtest_ours.csv (our days) and seq_backtest_teams.csv (top teams' own job counts)."""
import os, pandas as pd, sys
from fastshop import solve, lower_bound
from flowshop import load_ptt, DOW
OUT = 'data_all'; ME = '26_DKU_GMG'
TOP = sys.argv[2].split(',') if len(sys.argv) > 2 else ['26_SMART_FACTORY', '26_KGU_SCM9', '26_MJU1', '26_DKU_HIDDEN', '26_DGU_KSH', '26_DGU_LUCKY', '26_DKU_RM']
rows = []
for f in os.listdir(OUT):
    if f.endswith('_production0.csv'):
        b = pd.read_csv(f'{OUT}/{f}'); b['team'] = f[:-len('_production0.csv')]; rows.append(b)
B = pd.concat(rows); B = B[(B.Status == 'Produced') & (B['Planned #Jobs'] > 0) & B.Makespan.notna()].copy()
B['n'] = B['Planned #Jobs'].astype(int); B['dow'] = pd.to_datetime(B.Date).dt.dayofweek.map(lambda i: DOW[i]); B['ms'] = B.Makespan.astype(int)
B = B[B['Produced Qty'] == B.n * 1000]                      # full production only (material shortage cuts the job list)
cost = lambda ms: (ms // 100) * 100000 + max(0, ms // 100 - 70) * 100000
TAG = sys.argv[3] if len(sys.argv) > 3 else ''
secs = {'P1': float(sys.argv[1]) if len(sys.argv) > 1 else 40, 'P2': 3}
res = []
for _, r in B[B.team == ME].sort_values(['Date', 'Product']).iterrows():
    p = r['Product']; seq, ms = solve(p, r.dow, r.n, secs[p])
    o = B[(B.Date == r.Date) & (B['Product'] == p) & (B.n == r.n) & (B.team != ME)]
    res.append(dict(date=r.Date, product=p, dow=r.dow, n=r.n, board=r.ms, new=ms, lb=lower_bound(load_ptt(p, r.dow, r.n)),
                    best_other_same_n=int(o.ms.min()) if len(o) else None, hours_board=r.ms // 100, hours_new=ms // 100, saving=cost(r.ms) - cost(ms)))
    print(res[-1], flush=True)
pd.DataFrame(res).to_csv(f'seq_backtest_ours{TAG}.csv', index=False)
res = []
for _, r in B[B.team.isin(TOP) & (B['Product'] == 'P1')].sort_values(['Date', 'team']).iterrows():
    seq, ms = solve('P1', r.dow, r.n, secs['P1'] / 2)
    res.append(dict(date=r.Date, team=r.team, n=r.n, theirs=r.ms, ours_new=ms, diff_pct=round(100 * (ms - r.ms) / r.ms, 2), hours_theirs=r.ms // 100, hours_ours=ms // 100))
    print(res[-1], flush=True)
pd.DataFrame(res).to_csv(f'seq_backtest_teams{TAG}.csv', index=False)
print('DONE')
