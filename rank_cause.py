"""Why the rank moves: weekly profit components of our team vs the current top 10 (economic view).
value(date) = cumulative balance + material stock at cost + finished goods (P1 185, P2 280). Uses data_all/ (team_compare.py fetch)."""
import pandas as pd, numpy as np
from team_compare import summary
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40)
ME = '26_DKU_GMG'
L, S, D, R = summary(); L = L.reset_index(drop=True)
L['q'] = pd.to_numeric(L.Description.astype(str).str.extract(r'^(\d+) items')[0], errors='coerce').fillna(0)
st = L[L.cat.isin(['fg_hold', 'mat_hold'])].copy(); st['k'] = st.Action.str[-2:]
st['val'] = st.q * st.k.map({'P1': 185, 'P2': 280, 'M1': 30, 'M2': 25, 'M3': 50})
SV = st.pivot_table(index='Date', columns='team', values='val', aggfunc='sum', fill_value=0).reindex(D.index).fillna(0)
V = D + SV                                           # economic value by day
VR = V.rank(axis=1, ascending=False, method='min'); BR = R
days = list(D.index)
print('our rank by day   (balance / economic value)')
print(pd.DataFrame({'bal_rank': BR[ME].astype(int), 'val_rank': VR[ME].astype(int), 'bal_M': (D[ME] / 1e6).round(1), 'val_M': (V[ME] / 1e6).round(1),
                    'gap_to_10th_val_M': ((V[ME] - V.apply(lambda r: r.nlargest(10).iloc[-1], axis=1)) / 1e6).round(1)}).iloc[::2].to_string())
weeks = [('w1 11/01-07', '2026-11-01', '2026-11-07'), ('w2 11/08-14', '2026-11-08', '2026-11-14'), ('w3 11/15-21', '2026-11-15', '2026-11-21'), ('w4 11/22-23', '2026-11-22', '2026-11-23')]
top = [t for t in V.iloc[-1].sort_values(ascending=False).index if t != ME][:10]
pr = L[L.cat.str.startswith('prod_')].copy(); pr['p'] = pr.Action.str[-2:]
mp = L[L.cat.isin(['mat_normal', 'mat_urgent'])].copy()
mp['fee'] = pd.to_numeric(mp.Description.str.extract(r'\+ \$(\d+)')[0], errors='coerce').fillna(0); mp['m'] = mp.Action.str.extract(r'PURCHASE_(M\d)')[0]
mp['prem'] = np.where(mp.cat == 'mat_urgent', mp.Expense - mp.q * mp.m.map({'M1': 30, 'M2': 25, 'M3': 50}) - mp.fee, 0.0)
so = L[L.cat == 'stockout'].copy()
rows = []
for name, a, b in weeks:
    W = L[(L.Date >= a) & (L.Date <= b)]
    prev = [d for d in days if d < a]; v0 = V.loc[prev[-1]] if prev else 0 * V.iloc[0]
    v1 = V.loc[max(d for d in days if d <= b)]
    g = W.pivot_table(index='team', columns='cat', values='net', aggfunc='sum', fill_value=0)
    pw = pr[(pr.Date >= a) & (pr.Date <= b)]; mw = mp[(mp.Date >= a) & (mp.Date <= b)]
    u = pw.pivot_table(index='team', columns='p', values='q', aggfunc='sum', fill_value=0)
    c = pw.pivot_table(index='team', columns='p', values='Expense', aggfunc='sum', fill_value=0)
    T = pd.DataFrame({'gain': v1 - v0, 'revenue': g.get('rev_P1', 0) + g.get('rev_P2', 0), 'stockout': g.get('stockout', 0),
                      'fg_hold': g.get('fg_hold', 0), 'mat_hold': g.get('mat_hold', 0), 'fees': -mw.groupby('team').fee.sum(), 'urgent_prem': -mw.groupby('team').prem.sum(),
                      'P1_units_k': u.get('P1', 0) / 1e3, 'P1_cost_per_unit': c.get('P1', 0) / u.get('P1', 1), 'P2_units_k': u.get('P2', 0) / 1e3, 'P2_cost_per_unit': c.get('P2', 0) / u.get('P2', 1)}).fillna(0)
    for col in ['gain', 'revenue', 'stockout', 'fg_hold', 'mat_hold', 'fees', 'urgent_prem']: T[col] /= 1e6
    T['P1_prod_cost'] = -c.get('P1', 0) / 1e6; T['P2_prod_cost'] = -c.get('P2', 0) / 1e6
    T = T.fillna(0)
    r = pd.DataFrame({'us': T.loc[ME], 'top10_median': T.loc[top].median(), 'top10_best': T.loc[top].max()}); r['us_minus_median'] = r.us - r.top10_median
    r['our_rank_of_71'] = [int((T[k] > T.loc[ME, k]).sum() + 1) for k in r.index]
    print(f'\n== {name} =='); print(r.round(1).to_string())
    rows.append(r.us_minus_median.rename(name))
print('\n== us minus top-10 median, by week ($M; units/cost rows in their own units) =='); X = pd.concat(rows, axis=1); X['total'] = X.sum(axis=1); print(X.round(1).to_string())
