"""Probability of finishing in the top 10 (final Balance on 12/04, leftover stock worth 0).
python rank_mc.py [paths=4000]      needs data_all/ (python team_compare.py fetch AFTER the Saturday lock) and data/.
Prices: bootstrap of the last 60 daily log returns (Samsung on trading days, BTC daily), optional Monday shift for Samsung.
Every team: locked plan from its public production board, finished goods after the last ledger day, production cost = our cost
table x the team's own past ratio, holding $30/unit/day, stockout $250/unit, finished goods left on 12/04 worth 0.
Other teams' material shortages, order fees and reactions are NOT modelled; their leftover material = ALPHA x the lowest material
value they held since 11/09. Our team: P1 Friday capped at 158 jobs by M2, cut further through the Monday M1 order when Monday's
price is low, raised up to 187 by an urgent M2 order when Tuesday's price is high (fee 3M + extra M1 order 1M + $50/unit)."""
import sys, numpy as np, pandas as pd, planner
from team_compare import summary, OUT
from sim import load_demand
ME, END = '26_DKU_GMG', pd.Timestamp('2026-12-04')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
planner._load(); C = planner._cost
L, S, D, R = summary(); L = L.reset_index(drop=True); last = L.Date.max()
days = pd.date_range(pd.Timestamp(last) + pd.Timedelta(days=1), END)
L['q'] = pd.to_numeric(L.Description.astype(str).str.extract(r'^(\d+) items')[0], errors='coerce').fillna(0)
st = L[L.cat.isin(['fg_hold', 'mat_hold'])].copy(); st['k'] = st.Action.str[-2:]
st['val'] = st.q * st.k.map({'P1': 185, 'P2': 280, 'M1': 30, 'M2': 25, 'M3': 50})
now = st[st.Date == last]
V0 = D.loc[last] + now.groupby('team').val.sum().reindex(D.columns).fillna(0)
fg0 = now[now.cat == 'fg_hold'].pivot_table(index='team', columns='k', values='q', aggfunc='sum', fill_value=0)
fgval0 = now[now.cat == 'fg_hold'].groupby('team').val.sum().reindex(D.columns).fillna(0)
floor = st[(st.cat == 'mat_hold') & (st.Date >= '2026-11-09')].pivot_table(index='Date', columns='team', values='val', aggfunc='sum', fill_value=0).min().reindex(D.columns).fillna(0)
pr = L[L.cat.str.startswith('prod_') & (L.Date >= '2026-11-08') & (L.q > 0)].copy(); pr['p'] = pr.Action.str[-2:]
pr['tab'] = [int(C[(p, planner.dow_of(pd.Timestamp(d)))][min(int(q // 1000), planner.MAX_JOBS)]) for p, d, q in zip(pr.p, pr.Date, pr.q)]
ratio = (pr.groupby(['team', 'p']).Expense.sum() / pr.groupby(['team', 'p']).tab.sum()).unstack().clip(0.9, 1.5)
PRICE, MAT = {'P1': 250, 'P2': 350}, {'P1': 80, 'P2': 100}
H = load_demand('data'); rng = np.random.default_rng(3)
IMPUTE = int(sys.argv[2]) if len(sys.argv) > 2 else 0      # P1 jobs/day assumed for teams whose board shows no plan (0 = take the board literally)
imputed = []


def paths(prod, shift):
    h = H[prod]; ds = sorted(h); v = np.array([h[d] for d in ds][-61:], float); r = np.diff(np.log(v)); r -= r.mean()
    out = {}; p = np.full(N, float(h[ds[-1]])); first = True
    for d in days:
        if d <= ds[-1]: out[d] = np.full(N, float(h[d])) if (prod == 'P2' or planner.is_trading(d)) else np.zeros(N); continue
        if prod == 'P1' and not planner.is_trading(d): out[d] = np.zeros(N); continue
        p = p * np.exp(rng.choice(r, N) + (shift if (first and prod == 'P1') else 0.0)); first = False; out[d] = np.round(p)
    return out


def cost(t, p, d, n):                                        # n: int array of jobs
    tab = np.asarray(C[(p, planner.dow_of(d))], float)
    k = ratio.loc[t, p] if (t in ratio.index and not np.isnan(ratio.loc[t, p])) else 1.0
    return np.where(n > 0, tab[np.minimum(n, planner.MAX_JOBS)] * k, 0.0)


def run(shift, alpha, mine=None, cap=158, mx=187, flat=None):
    DEM = {'P1': paths('P1', shift), 'P2': paths('P2', 0.0)}; res = {}
    if flat is not None:                                     # deterministic: Samsung at last value x (1 + flat) all week, BTC unchanged
        p0 = H['P1'][max(H['P1'])]; b0 = H['P2'][max(H['P2'])]
        DEM = {'P1': {d: np.full(N, p0 * (1 + flat) if planner.is_trading(d) else 0.0) for d in days}, 'P2': {d: np.full(N, float(H['P2'].get(d, b0))) for d in days}}
    for t in D.columns:
        try: P = pd.read_csv(f'{OUT}/{t}_production0.csv')
        except Exception: continue
        j = {(d, p): int(n) for d, p, n in zip(P.Date, P.Product, pd.to_numeric(P['Planned #Jobs'], errors='coerce').fillna(0))}
        wk_ = [str(x.date()) for x in days if x > pd.Timestamp('2026-11-28')]
        s1 = sum(j.get((x, 'P1'), 0) for x in wk_); s2 = sum(j.get((x, 'P2'), 0) for x in wk_)
        if IMPUTE and t != ME and (s1 == 0 or s2 == 0):      # a product with no plan visible: assume a pack-like plan for it
            f1 = float(fg0.loc[t, 'P1']) if (t in fg0.index and 'P1' in fg0.columns) else 0.0; f2 = float(fg0.loc[t, 'P2']) if (t in fg0.index and 'P2' in fg0.columns) else 0.0
            need1 = IMPUTE * 5 * 1000 - f1; f2 = max(0.0, f2 - 59430) if last < '2026-11-28' else f2      # Saturday's P2 sale, if not in the ledger yet
            for x in wk_:
                if s1 == 0 and planner.is_trading(pd.Timestamp(x)): n_ = int(np.clip(np.ceil(min(need1, IMPUTE * 1000) / 1000), 0, IMPUTE)) if x == wk_[1] else IMPUTE; j[(x, 'P1')] = n_
                if s2 == 0: n2 = int(max(0, np.ceil((59800 - f2) / 1000))); f2 = max(0.0, f2 + n2 * 1000 - 59430); j[(x, 'P2')] = n2
            imputed.append(t)
        if t == ME and mine:
            for d_, n_ in mine.items(): j[(d_, 'P1')] = n_
        A3 = sum(j.get((x, 'P1'), 0) for x in ('2026-12-01', '2026-12-02', '2026-12-03')) * 1000; A2 = sum(j.get((x, 'P1'), 0) for x in ('2026-12-02', '2026-12-03')) * 1000
        dv = np.zeros(N); extra = np.zeros(N)
        for p in ['P1', 'P2']:
            fg = np.full(N, float(fg0.loc[t, p]) if (t in fg0.index and p in fg0.columns) else 0.0)
            fri = None
            for d in days:
                n = np.full(N, j.get((str(d.date()), p), 0))
                if t == ME and p == 'P1' and d == END: n = fri
                dem = DEM[p][d]
                fg = fg + n * 1000; sold = np.minimum(fg, dem); fg = fg - sold
                dv += sold * PRICE[p] - (dem - sold) * 250 - cost(t, p, d, n) - n * 1000 * MAT[p] - fg * 30
                if t == ME and p == 'P1' and d == pd.Timestamp('2026-11-30'):      # Monday: M1 order fixes Friday's ceiling (<= 158)
                    proj = np.maximum(0, fg + A3 - 3 * dem); fri = np.clip(np.ceil((dem * 1.01 - proj) / 1000), 0, cap).astype(int)
                if t == ME and p == 'P1' and d == pd.Timestamp('2026-12-01'):      # Tuesday: urgent M2 (+ M1) if the gap is large
                    proj = np.maximum(0, fg + A2 - 2 * dem); short = dem * 1.01 - proj - fri * 1000
                    add = np.where((fri == cap) & (short > 15000), np.minimum(mx - cap, np.ceil(short / 1000)), 0).astype(int)
                    extra += np.where(add > 0, 4e6 + add * 1000 * 50, 0.0) + 0.0; fri = fri + add
            if t == ME and p == 'P1': extra += np.maximum(0, cap - np.minimum(fri, cap)) * 50000.0      # M2 bought but not used
        left = 0.85e6 if t == ME else alpha * floor[t]
        res[t] = V0[t] - fgval0[t] + dv - extra - left
    F = pd.DataFrame(res); rank = F.rank(axis=1, ascending=False, method='min')[ME].values
    wk = np.mean([DEM['P1'][d] for d in days if planner.is_trading(d) and d > pd.Timestamp(last) + pd.Timedelta(days=1)], axis=0) / H['P1'][max(H['P1'])] - 1
    return rank, wk, F


if __name__ == '__main__':
    print(f'ledger to {last}, {N} paths, days {days[0].date()}..{days[-1].date()}, impute {IMPUTE}')
    for shift, nm in [(0.0, 'no drift'), (0.025, 'Monday +2.5% (US signal true)')]:
        for alpha in (0.0, 0.5, 1.0):
            rank, wk, F = run(shift, alpha)
            print(f'{nm:30s} others leftover x{alpha:.1f}: P(top10) {100*(rank<=10).mean():5.1f}%  median rank {np.median(rank):.0f}  10-90% {np.percentile(rank,10):.0f}-{np.percentile(rank,90):.0f}')
            if alpha == 0.5:
                for a, b in [(-1, -0.05), (-0.05, -0.02), (-0.02, 0.02), (0.02, 0.05), (0.05, 1)]:
                    m = (wk > a) & (wk <= b)
                    if m.sum(): print(f'      week-average Samsung {a*100:+.0f}%..{b*100:+.0f}%  ({100*m.mean():4.1f}% of paths): P(top10) {100*(rank[m]<=10).mean():5.1f}%  median rank {np.median(rank[m]):.0f}')
                med = F.median().sort_values(ascending=False)
                print('      median final balance, top 14:', ', '.join(f'{t[3:]} {v/1e6:.0f}' for t, v in med.head(14).items()))
