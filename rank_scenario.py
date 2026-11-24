"""Rank at the end of the locked week if demand stays flat: python rank_scenario.py <P1 demand> <P2 demand> [first day] [last day]
Every team's entered plan (public production board) + finished goods after the last ledger day; value = balance + stock at cost
(P1 185, P2 280, materials at price). Production cost = our cost table scaled by each team's own past cost ratio. Other teams'
material shortages and order fees are not modelled. Needs data_all/ (python team_compare.py fetch)."""
import sys, os, pandas as pd, numpy as np, planner
from team_compare import summary, OUT
ME = '26_DKU_GMG'
d1, d2 = float(sys.argv[1]), float(sys.argv[2])
planner._load(); C = planner._cost
L, S, D, R = summary(); L = L.reset_index(drop=True); last = L.Date.max()
first = sys.argv[3] if len(sys.argv) > 3 else str((pd.Timestamp(last) + pd.Timedelta(days=1)).date())
end = sys.argv[4] if len(sys.argv) > 4 else str((pd.Timestamp(first) + pd.Timedelta(days=(5 - pd.Timestamp(first).weekday()) % 7)).date())
days = pd.date_range(first, end)
L['q'] = pd.to_numeric(L.Description.astype(str).str.extract(r'^(\d+) items')[0], errors='coerce').fillna(0)
st = L[L.cat.isin(['fg_hold', 'mat_hold']) & (L.Date == last)].copy(); st['k'] = st.Action.str[-2:]
st['val'] = st.q * st.k.map({'P1': 185, 'P2': 280, 'M1': 30, 'M2': 25, 'M3': 50})
V0 = D.loc[last] + st.groupby('team').val.sum().reindex(D.columns).fillna(0)
fg0 = st[st.cat == 'fg_hold'].pivot_table(index='team', columns='k', values='q', aggfunc='sum', fill_value=0)
pr = L[L.cat.str.startswith('prod_') & (L.Date >= '2026-11-08') & (L.q > 0)].copy(); pr['p'] = pr.Action.str[-2:]
pr['tab'] = [int(C[(p, planner.dow_of(pd.Timestamp(d)))][min(int(q // 1000), planner.MAX_JOBS)]) for p, d, q in zip(pr.p, pr.Date, pr.q)]
ratio = (pr.groupby(['team', 'p']).Expense.sum() / pr.groupby(['team', 'p']).tab.sum()).unstack().clip(0.9, 1.5)
PRICE, MAT, FGV, DEM = {'P1': 250, 'P2': 350}, {'P1': 80, 'P2': 100}, {'P1': 185, 'P2': 280}, {'P1': d1, 'P2': d2}
rows = []
for t in D.columns:
    try: P = pd.read_csv(f'{OUT}/{t}_production0.csv')
    except Exception: continue
    j = {(d, p): int(n) for d, p, n in zip(P.Date, P.Product, P['Planned #Jobs'])}
    dv = 0; short = {'P1': 0, 'P2': 0}; fgend = {}
    for p in ['P1', 'P2']:
        fg = float(fg0.loc[t, p]) if t in fg0.index and p in fg0.columns else 0.0; f0 = fg
        for d in days:
            n = j.get((str(d.date()), p), 0); dem = DEM[p] if (p == 'P2' or planner.is_trading(d)) else 0
            cost = int(C[(p, planner.dow_of(d))][min(n, planner.MAX_JOBS)]) * (ratio.loc[t, p] if t in ratio.index and not np.isnan(ratio.loc[t, p]) else 1.0) if n else 0
            fg += n * 1000; sold = min(fg, dem); fg -= sold; short[p] += dem - sold
            dv += sold * PRICE[p] - (dem - sold) * 250 - cost - n * 1000 * MAT[p] - fg * 30
        dv += (fg - f0) * FGV[p]; fgend[p] = fg
    rows.append((t, V0[t] / 1e6, dv / 1e6, short['P1'] / 1e3, short['P2'] / 1e3, fgend['P1'] / 1e3, fgend['P2'] / 1e3))
T = pd.DataFrame(rows, columns=['team', 'value_now', 'change', 'P1_short_k', 'P2_short_k', 'P1_fg_end_k', 'P2_fg_end_k']).set_index('team')
T['value_end'] = T.value_now + T.change; T['rank_now'] = T.value_now.rank(ascending=False).astype(int); T['rank_end'] = T.value_end.rank(ascending=False).astype(int)
T = T.sort_values('value_end', ascending=False)
pd.set_option('display.width', 250)
print(f'scenario P1 {d1:,.0f} / P2 {d2:,.0f} from {first} to {end} (ledger to {last})')
print(T.head(18).round(1).to_string())
print('\nours:', T.loc[ME].round(1).to_dict()); print('gap to 10th: %.1fM' % (T.loc[ME, 'value_end'] - T.value_end.iloc[9]))
