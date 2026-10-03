"""IOG daily-operations simulator. Reproduces the Ledger from a plan + actual demand.

Rules (all verified against team 26_DKU_GMG ledger, R2602A 9/13-9/17):
  * Day order: material arrivals (usable same day) -> production -> sales -> inventory charges.
  * Production: jobs made = min(planned, floor(material/need)); jobs are IDs 1..k, so when
    material is short only the first k IDs are produced and re-sequenced.
    cost = setup (if k>0) + hours*LABOR + max(0, hours-70)*LABOR,  hours = floor(makespan/100).
  * Sales: sold = min(inventory + produced, demand); unmet demand is lost at $250/unit.
  * Inventory: product $30/unit/day, material M1 $1, M2 $1, M3 $2 charged on end-of-day level.
  * Purchases: unit cost + order cost charged on the ARRIVAL day.
  * Demand: P1 (005930) only on KRX trading days, P2 (BTC) every day.
"""
import numpy as np, pandas as pd, datetime as dt
from flowshop import load_ptt, makespan, DOW

CFG = dict(
    price={'P1': 250, 'P2': 350}, setup={'P1': 5_000_000, 'P2': 4_000_000},
    labor=100_000, capa_h=70, items_per_job=1000, inv_cost=30, stockout=250,
    bom={'P1': {'M1': 1, 'M2': 2}, 'P2': {'M3': 1, 'M2': 2}},
    mat_unit={'M1': 30, 'M2': 25, 'M2U': 50, 'M3': 50}, mat_order={'M1': 1_000_000, 'M2': 3_000_000, 'M2U': 3_000_000, 'M3': 2_000_000},
    mat_lt={'M1': 3, 'M2': 8, 'M2U': 2, 'M3': 5}, mat_hold={'M1': 1, 'M2': 1, 'M3': 2},
    init_mat={'M1': 300_000, 'M2': 3_000_000, 'M3': 500_000},
)


def dow_of(d):
    return DOW[pd.Timestamp(d).weekday()]


def make_day(product, d, planned_jobs, seq, mat, ptt_cache=None):
    """Produce up to planned_jobs of product on date d. seq = list of 1-based job IDs (or None => SPT).
    Returns (jobs_made, makespan, cost_dict) and mutates mat."""
    if planned_jobs <= 0:
        return 0, 0, dict(labor=0, ext=0, setup=0)
    k = planned_jobs
    for m, q in CFG['bom'][product].items():
        k = min(k, mat[m] // (q * CFG['items_per_job']))
    if k <= 0:
        return 0, 0, dict(labor=0, ext=0, setup=0)
    P = load_ptt(product, dow_of(d), k)
    if seq is None:
        order = list(np.argsort(P[:, 0]))              # system AUTO = SPT on machine-1 time
    else:
        order = [j - 1 for j in seq if j <= k]        # keep only produced IDs, preserve order
    ms = makespan(P, order)
    hours = ms // 100
    cost = dict(labor=hours * CFG['labor'], ext=max(0, hours - CFG['capa_h']) * CFG['labor'], setup=CFG['setup'][product])
    for m, q in CFG['bom'][product].items():
        mat[m] -= q * k * CFG['items_per_job']
    return k, ms, cost


def simulate(days, demand, plan, orders, init_mat=None, init_inv=None, verbose=False):
    """days: list of dates. demand: {product: {date: qty}}.
    plan: {date: {product: (jobs, seq_or_None)}}.  orders: list of (arrival_date, material, qty, urgent).
    Returns (ledger DataFrame, summary dict)."""
    mat = dict(init_mat or CFG['init_mat'])
    inv = dict(init_inv or {'P1': 0, 'P2': 0})
    rows = []
    add = lambda d, action, rev, exp, desc: rows.append(dict(Date=str(pd.Timestamp(d).date()), Action=action, Revenue=rev, Expense=exp, Description=desc))
    for d in days:
        d = pd.Timestamp(d)
        for arr, m, q, urgent in orders:
            if pd.Timestamp(arr) == d:
                key = 'M2U' if (m == 'M2' and urgent) else m
                mat[m] += q
                add(d, f'MATERIAL_PURCHASE_{m}_{"URGENT" if urgent else "NORMAL"}', 0, q * CFG['mat_unit'][key] + CFG['mat_order'][key], f'{q} items')
        for p in ['P1', 'P2']:
            jobs, seq = plan.get(d, {}).get(p, (0, None))
            k, ms, c = make_day(p, d, jobs, seq, mat)
            if k:
                add(d, f'PRODUCTION_{p}', 0, sum(c.values()), f'{k*1000} items ms={ms} labor={c["labor"]} ext={c["ext"]} setup={c["setup"]}')
                inv[p] += k * CFG['items_per_job']
        for p in ['P1', 'P2']:
            dem = demand[p].get(d, 0)
            sold = min(inv[p], dem)
            inv[p] -= sold
            if sold:
                add(d, f'SALES_{p}', sold * CFG['price'][p], 0, f'{sold} items')
            if dem - sold > 0:
                add(d, f'STOCKOUT_{p}', 0, (dem - sold) * CFG['stockout'], f'{dem-sold} items')
            add(d, f'SALES_INVENTORY_{p}', 0, inv[p] * CFG['inv_cost'], f'{inv[p]} items')
        for m in ['M1', 'M2', 'M3']:
            add(d, f'MATERIAL_INVENTORY_{m}', 0, mat[m] * CFG['mat_hold'][m], f'{mat[m]} items')
    L = pd.DataFrame(rows)
    s = dict(revenue=L.Revenue.sum(), expense=L.Expense.sum(), profit=L.Revenue.sum() - L.Expense.sum(), end_mat=mat, end_inv=inv)
    return L, s


def load_demand(path='data'):
    out = {}
    for p, code in [('P1', '005930'), ('P2', 'BTC')]:
        d = pd.read_csv(f'{path}/demand_{code}.csv', parse_dates=['DATE'])
        out[p] = {pd.Timestamp(r.DATE): int(r.DEMAND_QTY) for r in d.itertuples()}
    return out
