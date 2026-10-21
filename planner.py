"""Weekly planner: forecast -> job quantities -> P2 day allocation (DP) -> material orders -> sequences.



Usage:  python planner.py --asof 2026-09-26 --round R2602B --start 2026-09-27 --end 2026-10-16

Outputs plans/<round>_<week_start>.json  (+ .md summary to paste into the dashboard)

"""

import argparse, json, os, math

import numpy as np, pandas as pd

from flowshop import load_ptt, makespan, spt, neh, iterated_greedy, DOW

from sim import CFG, dow_of



HERE = os.path.dirname(os.path.abspath(__file__))

# KRX closed weekdays (verified against demand history: substitute holidays DO close the market)

# 9/28 was OPEN (Chuseok's Saturday overlap does not create a substitute day); 10/5 = National Foundation Day (Sat 10/3) substitute

KRX_HOLIDAYS = {'2026-09-24', '2026-09-25', '2026-10-05', '2026-10-09', '2026-12-25', '2026-12-31'}

# forecast error std by horizon (from demand history, see analysis): P1 by trading days, P2 by calendar days

SIGMA = {'P1': [0, .033, .045, .052, .059, .065, .07, .075], 'P2': [0, .021, .031, .037, .043, .049, .054, .059]}

MAX_JOBS = 500



_table = None

_cost = {}

def _load():

    """Precompute labor+setup cost arrays (index = jobs 0..500) from the NEH makespan table."""

    global _table

    t = pd.read_csv(f'{HERE}/ms_table.csv')

    _table = {}

    for (p, d), g in t.groupby(['product', 'dow']):

        ns = np.arange(0, MAX_JOBS + 1)

        hours = (np.interp(ns, g.n.values, g.neh.values).astype(int)) // 100

        cost = CFG['setup'][p] + hours * CFG['labor'] + np.maximum(0, hours - CFG['capa_h']) * CFG['labor']

        cost[0] = 0; hours[0] = 0

        _table[(p, d)] = hours; _cost[(p, d)] = cost



def ms_hours(product, dow, n):

    """NEH makespan hours (floor(ms/100)) from the precomputed table, linear interpolation in n."""

    if _table is None: _load()

    return int(_table[(product, dow)][max(0, min(n, MAX_JOBS))])



def labor_cost(product, dow, n):

    if _table is None: _load()

    return int(_cost[(product, dow)][max(0, min(n, MAX_JOBS))])



def is_trading(d):

    d = pd.Timestamp(d)

    return d.weekday() < 5 and str(d.date()) not in KRX_HOLIDAYS



def forecast(hist, product, days, z):

    """Naive forecast (last close) + safety by horizon. hist: {date: qty}. Returns {day: (forecast, target_qty)}."""

    last_date = max(hist); last = hist[last_date]

    out, h = {}, 0

    for d in days:

        d = pd.Timestamp(d)

        if product == 'P1' and not is_trading(d):

            out[d] = (0, 0); continue

        h += 1

        sig = SIGMA[product][min(h, 7)]

        out[d] = (last, int(round(last * (1 + z * sig))))

    return out



def allocate(product, days, target, inv0, lookahead=None, round_end=None):

    """DP over days: choose jobs/day to cover cumulative target (in jobs) at min setup+labor+holding.

    State = carried inventory (jobs). Production is allowed ahead of demand only for P2 (P1 too, DP decides).

    lookahead: extra {day: jobs} demand after the week that may be pre-built (only if before round_end)."""

    # Rolling horizon: the DP also covers the look-ahead days (next Sun/Mon) at their real weekday cost, so a

    # Friday prebuild gets credit for skipping next Sunday's expensive run. Only this week's decisions are returned.

    week_len = len(days)

    look = [pd.Timestamp(d) for d in sorted(lookahead or {}) if round_end is None or pd.Timestamp(d) <= pd.Timestamp(round_end)]

    horizon = [pd.Timestamp(d) for d in days] + look

    tgt = {**{pd.Timestamp(d): v for d, v in target.items()}, **{pd.Timestamp(d): lookahead[d] for d in (lookahead or {})}}

    dem = [math.ceil(tgt[d] / 1000) for d in horizon]

    extra = 0

    T = len(horizon)

    hold = CFG['inv_cost'] * 1000  # per job per day

    # dp[t][s] = min cost with inventory s (jobs) at end of day t

    dp = [{} for _ in range(T + 1)]

    dp[0][inv0] = (0, None)

    for t, d in enumerate(horizon):

        dow = dow_of(d)

        need = dem[t]

        remaining_after = sum(dem[t + 1:]) + extra

        for s, (c, _) in dp[t].items():

            # produce x jobs so that s + x >= need (no stockout by design); cap inventory to remaining demand

            lo = max(0, need - s)

            hi = max(lo, min(MAX_JOBS, need + remaining_after - s))   # inventory may exceed remaining demand -> allow x=0

            if product == 'P1':   # makespan is flat across weekdays -> building ahead never beats $30k/job/day holding

                hi = lo

            if _table is None: _load()

            carr = _cost[(product, dow)]

            nxt = dp[t + 1]

            for x in range(lo, hi + 1):

                s2 = s + x - need

                c2 = c + int(carr[x]) + s2 * hold

                if s2 not in nxt or c2 < nxt[s2][0]:

                    nxt[s2] = (c2, (s, x))

    best_s = min(dp[T], key=lambda s: dp[T][s][0])

    plan, s = [], best_s

    for t in range(T, 0, -1):

        prev, x = dp[t][s][1]

        plan.append(x); s = prev

    plan = plan[::-1][:week_len]

    return dict(zip([pd.Timestamp(d) for d in days], plan)), dp[T][best_s][0]



def material_orders(prod_plan, mat0, pending, days_horizon, asof, round_start, round_end, T_int={'M1': 3, 'M2': 3, 'M3': 5}):

    """prod_plan: {day: {product: jobs}}. Returns list of orders (place_date, material, qty, arrival, urgent) + shortage warnings.

    Policy: project inventory; when it would go negative on day d, an order covering T days of need must arrive on d.

    Place at d - LT (>= asof+1, >= round_start). If too late: M2 -> urgent; M1/M3 -> warn (production must be cut)."""

    need = {}

    for d, prods in prod_plan.items():

        for p, jobs in prods.items():

            for m, q in CFG['bom'][p].items():

                need.setdefault(pd.Timestamp(d), {}).setdefault(m, 0)

                need[pd.Timestamp(d)][m] += q * jobs * 1000

    orders, warns = [], []

    first_place = max(pd.Timestamp(asof) + pd.Timedelta(days=1), pd.Timestamp(round_start))

    for m in ['M1', 'M2', 'M3']:

        inv = mat0[m]

        arrivals = {}

        for (arr, mm, q, u) in pending:

            if mm == m:

                arrivals[pd.Timestamp(arr)] = arrivals.get(pd.Timestamp(arr), 0) + q

        for d in days_horizon:

            d = pd.Timestamp(d)

            inv += arrivals.get(d, 0)

            n = need.get(d, {}).get(m, 0)

            if inv < n:

                # cover from d through d+T-1 (plus what's short today)

                cover = sum(need.get(d + pd.Timedelta(days=i), {}).get(m, 0) for i in range(T_int[m])) - inv

                cover = int(math.ceil(max(cover, n - inv) / 1000) * 1000)

                lt = CFG['mat_lt'][m]; place = d - pd.Timedelta(days=lt); urgent = False

                if place < first_place and m == 'M2':

                    urgent = True; lt = CFG['mat_lt']['M2U']; place = d - pd.Timedelta(days=lt)

                if place < first_place:

                    warns.append(f'{m}: short {n-inv:,} on {d.date()} and no order can arrive in time (earliest place {first_place.date()}, LT {lt})')

                    inv = max(inv, 0)  # production will be cut by the sim

                    continue

                orders.append((str(place.date()), m, cover, str(d.date()), urgent))

                inv += cover

            inv -= min(n, inv)

    return orders, warns



Z_DEFAULT = {'P1': 0.4, 'P2': 0.4}   # tuned by backtest.py (2025-07..2026-09)



def build_week(asof, round_id, round_start, round_end, z=None, mat0=None, inv0=None, pending=(), ig_seconds=20, out_dir='plans', today=None):

    asof = pd.Timestamp(asof)

    from sim import load_demand

    hist = load_demand(f'{HERE}/data')

    hist = {p: {d: v for d, v in h.items() if d <= asof} for p, h in hist.items()}

    week_start = asof + pd.Timedelta(days=1)                       # Sunday

    days = [week_start + pd.Timedelta(days=i) for i in range(7)]

    days = [d for d in days if pd.Timestamp(round_start) <= d <= pd.Timestamp(round_end)]

    nxt = [days[-1] + pd.Timedelta(days=i) for i in range(1, 3)]   # look-ahead Sun/Mon of following week

    z = z or Z_DEFAULT

    fc = {p: forecast(hist[p], p, days + nxt, z[p]) for p in ['P1', 'P2']}

    prod_plan = {d: {} for d in days}

    alloc_cost = {}

    for p in ['P1', 'P2']:

        target = {d: fc[p][d][1] for d in days}

        look = {d: fc[p][d][1] for d in nxt}

        jobs, cost = allocate(p, days, target, (inv0 or {}).get(p, 0) // 1000, look, round_end)

        alloc_cost[p] = cost

        for d in days:

            prod_plan[d][p] = jobs[d]

    # material horizon: this week + 14 days, estimating later production as the daily target (P1 trading days, P2 daily)

    ext_days = [days[-1] + pd.Timedelta(days=i) for i in range(1, 15) if days[-1] + pd.Timedelta(days=i) <= pd.Timestamp(round_end)]

    fc_ext = {p: forecast(hist[p], p, days + ext_days, z[p]) for p in ['P1', 'P2']}

    mat_plan = dict(prod_plan)

    for d in ext_days:

        mat_plan[d] = {p: math.ceil(fc_ext[p][d][1] / 1000) for p in ['P1', 'P2']}

    place_from = pd.Timestamp(today) - pd.Timedelta(days=1) if today else asof   # material orders can start the day after this

    orders, warns = material_orders(mat_plan, mat0 or CFG['init_mat'], list(pending), days + ext_days, place_from, round_start, round_end)

    orders = [o for o in orders if o[0] <= str(days[-1].date()) or True]   # keep all; later weeks re-plan and overwrite

    # sequences

    seqs = {}

    for d in days:

        for p, n in prod_plan[d].items():

            if n > 0:

                P = load_ptt(p, dow_of(d), n)

                s_ms = makespan(P, spt(P)); q = neh(P)

                seq, ms = iterated_greedy(P, q, seconds=ig_seconds) if ig_seconds > 0 else (q, makespan(P, q))

                seqs[f'{d.date()}_{p}'] = dict(jobs=n, spt=s_ms, opt=ms, seq=[j + 1 for j in seq])

    plan = dict(round=round_id, asof=str(asof.date()), week=[str(d.date()) for d in days], z=z,

                forecast={p: {str(d.date()): fc[p][d][0] for d in days} for p in fc},

                target={p: {str(d.date()): fc[p][d][1] for d in days} for p in fc},

                jobs={str(d.date()): prod_plan[d] for d in days}, orders=orders, warnings=warns, sequences=seqs)

    os.makedirs(f'{HERE}/{out_dir}', exist_ok=True)

    path = f'{HERE}/{out_dir}/{round_id}_{days[0].date()}.json'

    json.dump(plan, open(path, 'w'), indent=1, default=int)

    open(path.replace('.json', '.md'), 'w', encoding='utf-8').write(render(plan))

    return plan, path



def render(plan):

    L = [f"# {plan['round']} weekly plan  (as of {plan['asof']}, z={plan['z']})", '',

         '## Demand forecast & production (enter Sat by 19:30, CUSTOM mode)', '',

         '| Day | P1 fcst | P1 target | P1 jobs | P1 hrs SPT->OPT | P2 fcst | P2 target | P2 jobs | P2 hrs SPT->OPT |', '|---|---|---|---|---|---|---|---|---|']

    for d in plan['week']:

        row = [f"{d} {DOW[pd.Timestamp(d).weekday()]}"]

        for p in ['P1', 'P2']:

            s = plan['sequences'].get(f'{d}_{p}')

            hrs = f"{s['spt']//100}->{s['opt']//100}" if s else '-'

            row += [f"{plan['forecast'][p][d]:,}", f"{plan['target'][p][d]:,}", str(plan['jobs'][d][p]), hrs]

        L.append('| ' + ' | '.join(row) + ' |')

    L += ['', '## Material orders (enter daily by 19:30)', '', '| Place on | Material | Qty | Type | Arrives |', '|---|---|---|---|---|']

    for pl, m, q, arr, u in plan['orders']:

        L.append(f'| {pl} | {m} | {q:,} | {"URGENT" if u else "NORMAL"} | {arr} |')

    if plan['warnings']:

        L += ['', '## WARNINGS', ''] + [f'- {w}' for w in plan['warnings']]

    L += ['', '## Job sequences (CUSTOM)', '']

    for k, s in plan['sequences'].items():

        L += [f"### {k}  ({s['jobs']} jobs, makespan {s['opt']} vs SPT {s['spt']})", '', '```', ','.join(map(str, s['seq'])), '```', '']

    return '\n'.join(L)



if __name__ == '__main__':

    ap = argparse.ArgumentParser()

    ap.add_argument('--asof', required=True); ap.add_argument('--round', required=True)

    ap.add_argument('--start', required=True); ap.add_argument('--end', required=True)

    ap.add_argument('--z', default=None, help='JSON {"P1":0.4,"P2":0.6}'); ap.add_argument('--ig', type=int, default=20)

    ap.add_argument('--mat', default=None, help='JSON {"M1":..,"M2":..,"M3":..}')

    ap.add_argument('--inv', default=None, help='JSON {"P1":..,"P2":..}')

    ap.add_argument('--pending', default=None, help='JSON [[arrival,material,qty,urgent],...]')

    ap.add_argument('--today', default=None, help='first day material orders can be placed (default asof+1)')

    a = ap.parse_args()

    plan, path = build_week(a.asof, a.round, a.start, a.end, json.loads(a.z) if a.z else None, json.loads(a.mat) if a.mat else None,

                            json.loads(a.inv) if a.inv else None, json.loads(a.pending) if a.pending else (), a.ig, today=a.today)

    print(render(plan)); print('\nsaved', path)

