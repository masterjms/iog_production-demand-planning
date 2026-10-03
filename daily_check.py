"""Virtual-round daily check: refresh demand + boards, replay our plan(s) through the simulator up to the
last known demand date, and compare with the team's actual ledger.

Usage: python daily_check.py --round R2602B --start 2026-09-27 --end 2026-10-16 [--team DKU/26_DKU_GMG] [--no-fetch]
Plans are read from plans/<round>_*.json (one per week); orders/sequences from all of them are merged.
"""
import argparse, glob, json, os, subprocess, sys
import pandas as pd
from sim import simulate, load_demand, CFG
from planner import is_trading

HERE = os.path.dirname(os.path.abspath(__file__))

def load_plans(round_id):
    plan, orders, fc = {}, [], {'P1': {}, 'P2': {}}
    files = sorted(glob.glob(f'{HERE}/plans/{round_id}_*.json'))
    for f in files:
        p = json.load(open(f))
        for d, prods in p['jobs'].items():
            plan[pd.Timestamp(d)] = {k: (n, p['sequences'].get(f'{d}_{k}', {}).get('seq')) for k, n in prods.items()}
        wk = set(p['week'])
        # a later week's plan overrides orders placed on/after its first day
        orders = [o for o in orders if o[0] < p['week'][0]] + [o for o in p['orders']]
        for k in fc:
            fc[k].update({pd.Timestamp(d): v for d, v in p['forecast'][k].items()})
    return plan, orders, fc, files

def actual_ledger(team, round_id):
    f = f'{HERE}/data/ledger_0.csv'
    if not os.path.exists(f):
        return None
    L = pd.read_csv(f)
    for c in ['Revenue', 'Expense']:
        L[c] = L[c].astype(str).str.replace(r'[\$,]', '', regex=True).astype(int)
    return L

def run(round_id, start, end, team, fetch=True, pending=()):
    if fetch:
        subprocess.run([sys.executable, f'{HERE}/fetch_board.py', team, round_id], check=False, capture_output=True)
        import requests, io
        for code in ['005930', 'BTC']:
            d = pd.read_excel(io.BytesIO(requests.get(f'http://play.ioground.kr:5005/plans_demand/demand_down/{code}').content), engine='xlrd')
            d['DATE'] = pd.to_datetime(d['DATE']); d.sort_values('DATE').to_csv(f'{HERE}/data/demand_{code}.csv', index=False)
    dem = load_demand(f'{HERE}/data')
    last = max(max(dem['P1']), max(dem['P2']))
    plan, orders, fc, files = load_plans(round_id)
    days = list(pd.date_range(start, min(pd.Timestamp(end), last)))
    if not days:
        print('no demand data inside the round yet (last demand', last.date(), ')'); return
    sim_orders = [(arr, m, q, u) for (_, m, q, arr, u) in orders] + list(pending)
    L, s = simulate(days, dem, plan, sim_orders)
    print(f'== Virtual {round_id} for {team}: {days[0].date()} .. {days[-1].date()} (plans: {[os.path.basename(f) for f in files]})')
    by = L.groupby('Action')[['Revenue', 'Expense']].sum()
    print(by[(by.Revenue > 0) | (by.Expense > 0)].to_string())
    print(f'\nVIRTUAL  revenue {s["revenue"]:>15,}  expense {s["expense"]:>15,}  profit {s["profit"]:>15,}  margin {100*s["profit"]/max(s["revenue"],1):.1f}%')
    A = actual_ledger(team, round_id)
    if A is not None:
        A = A[(A.Date >= str(days[0].date())) & (A.Date <= str(days[-1].date()))]
        ar, ae = A.Revenue.sum(), A.Expense.sum()
        print(f'ACTUAL   revenue {ar:>15,}  expense {ae:>15,}  profit {ar-ae:>15,}  (team board)')
        print(f'DELTA    {s["profit"]-(ar-ae):+,}')
    # per-day table
    rows = []
    for d in days:
        g = L[L.Date == str(d.date())]
        def val(a, col='Expense'): return int(g[g.Action == a][col].sum())
        rows.append(dict(date=str(d.date()), dow=d.strftime('%a'), P1_dem=dem['P1'].get(d, 0), P1_fc=fc['P1'].get(d, ''),
                         P2_dem=dem['P2'].get(d, 0), P2_fc=fc['P2'].get(d, ''),
                         P1_jobs=plan.get(d, {}).get('P1', (0,))[0], P2_jobs=plan.get(d, {}).get('P2', (0,))[0],
                         stockout=val('STOCKOUT_P1') + val('STOCKOUT_P2'), prod_cost=val('PRODUCTION_P1') + val('PRODUCTION_P2'),
                         revenue=int(g.Revenue.sum()), day_profit=int(g.Revenue.sum() - g.Expense.sum())))
    T = pd.DataFrame(rows); pd.set_option('display.width', 250)
    print('\n' + T.to_string(index=False))
    print('\nend inventory', s['end_inv'], 'end material', s['end_mat'])
    fe = [(abs(fc['P1'][d] - dem['P1'][d]) / dem['P1'][d]) for d in days if d in fc['P1'] and dem['P1'].get(d, 0) > 0]
    fe2 = [(abs(fc['P2'][d] - dem['P2'][d]) / dem['P2'][d]) for d in days if d in fc['P2'] and dem['P2'].get(d, 0) > 0]
    if fe or fe2:
        print(f'forecast MAPE  P1 {100*sum(fe)/max(len(fe),1):.2f}%   P2 {100*sum(fe2)/max(len(fe2),1):.2f}%')
    os.makedirs(f'{HERE}/reports', exist_ok=True)
    T.to_csv(f'{HERE}/reports/{round_id}_{days[-1].date()}.csv', index=False)
    L.to_csv(f'{HERE}/reports/{round_id}_{days[-1].date()}_ledger.csv', index=False)
    return s

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--round', required=True); ap.add_argument('--start', required=True); ap.add_argument('--end', required=True)
    ap.add_argument('--team', default='DKU/26_DKU_GMG'); ap.add_argument('--no-fetch', action='store_true')
    a = ap.parse_args()
    run(a.round, a.start, a.end, a.team, fetch=not a.no_fetch)
