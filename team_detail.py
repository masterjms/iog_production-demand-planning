import pandas as pd, numpy as np, re, os
from team_compare import summary, OUT, money
pd.set_option('display.width', 280); pd.set_option('display.max_columns', 40)
L, S, D, R = summary()
L = L.reset_index(drop=True)
# finished goods on hand (last ledger day) and avg stock
fg = L[L.cat == 'fg_hold'].copy(); fg['q'] = fg.Description.str.split().str[0].astype(float); fg['p'] = fg.Action.str[-2:]
last = L.Date.max()
fgl = fg[fg.Date == last].pivot_table(index='team', columns='p', values='q', aggfunc='sum').fillna(0)
S['fg_val'] = (fgl.get('P1', 0) * 185 + fgl.get('P2', 0) * 280).reindex(S.index).fillna(0)
S['true'] = S.adj + S.fg_val
# purchases: fees / urgent premium / consumption
mp = L[L.cat.isin(['mat_normal', 'mat_urgent'])].copy()
mp['qty'] = mp.Description.str.extract(r'^(\d+) items')[0].astype(float); mp['fee'] = mp.Description.str.extract(r'\+ \$(\d+)')[0].astype(float)
mp['m'] = mp.Action.str.extract(r'PURCHASE_(M\d)')[0]; mp['base'] = mp.qty * mp.m.map({'M1': 30, 'M2': 25, 'M3': 50})
S['fees'] = -mp.groupby('team').fee.sum(); S['n_orders'] = mp.groupby('team').size()
S[['fees','n_orders']] = S[['fees','n_orders']].fillna(0)
mp['prem'] = np.where(mp.cat == 'mat_urgent', mp.Expense - mp.base - mp.fee, 0.0)
S['urg_prem'] = -mp.groupby('team').prem.sum()
S['consumed'] = -(mp.groupby('team').base.sum().reindex(S.index).fillna(0) - S.mat_stock)
S['urg_prem'] = S.urg_prem.fillna(0)
# production detail
pr = L[L.cat.str.startswith('prod_')].copy()
pr['units'] = pr.Description.str.extract(r'^(\d+) items')[0].astype(float)
for k in ['labor', 'ext', 'setup']: pr[k] = pr.Description.str.extract(rf'{k}: (\d+)')[0].astype(float)
pr['dow'] = pd.to_datetime(pr.Date).dt.dayofweek; pr['p'] = pr.Action.str[-2:]
g = pr.groupby(['team', 'p']).agg(units=('units', 'sum'), cost=('Expense', 'sum'), ext=('ext', 'sum'), setup=('setup', 'sum'))
for p in ['P1', 'P2']:
    S[f'{p}_units_k'] = g.xs(p, level='p').units / 1e3; S[f'{p}_cost_per'] = g.xs(p, level='p').cost / g.xs(p, level='p').units
    S[f'{p}_ext'] = -g.xs(p, level='p').ext
w = pr[(pr.p == 'P2')].assign(we=lambda x: x.dow.isin([5, 6])).groupby(['team', 'we']).units.sum().unstack(fill_value=0)
S['P2_wkend_share'] = (w[True] / (w[True] + w[False])).reindex(S.index)
S['P2_fri_k'] = pr[(pr.p == 'P2') & (pr.dow == 4)].groupby('team').units.mean() / 1e3
S['P2_prod_days'] = pr[(pr.p == 'P2') & (pr.units > 0)].groupby('team').size()
# algo use
al = {}
for t in S.index:
    try:
        b = pd.read_csv(f'{OUT}/{t}_production0.csv'); b = b[(b.Status == 'Produced') & (b['Planned #Jobs'] > 0)]
        al[t] = '/'.join(f'{k}:{v}' for k, v in b.Algo.value_counts().items()) + ' ' + '/'.join(f'{k}:{v}' for k, v in b.Type.value_counts().items())
    except Exception as e: al[t] = '?'
S['algo'] = pd.Series(al)
S['rank'] = S.net.rank(ascending=False, method='min').astype(int); S['true_rank'] = S.true.rank(ascending=False, method='min').astype(int)
S['rank_1113'] = R.loc['2026-11-13'].astype(int)
S.to_csv('data_all/_summary.csv')
m = ['net', 'mat_stock', 'fg_val', 'true', 'rev_P1', 'rev_P2', 'stockout', 'prod_P1', 'prod_P2', 'consumed', 'fees', 'urg_prem', 'fg_hold', 'mat_hold']
top = S.sort_values('true', ascending=False)
out = (top[m] / 1e6).round(1); out.insert(0, 'rank', top['rank']); out.insert(1, 'true_rank', top.true_rank); out.insert(2, 'r1113', top.rank_1113)
print(out.head(22).to_string())
print()
print(top[['rank', 'true_rank', 'n_orders', 'P1_units_k', 'P1_cost_per', 'P2_units_k', 'P2_cost_per', 'P2_wkend_share', 'P2_fri_k', 'P2_prod_days', 'algo']].head(22).round(2).to_string())
