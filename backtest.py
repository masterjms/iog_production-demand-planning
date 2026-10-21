"""Rolling backtest of the weekly policy over real demand history (labor from NEH table, materials assumed available
at unit cost). Compares safety levels z and reports profit per week."""
import pandas as pd, numpy as np, math, sys
from sim import CFG, load_demand, dow_of
from planner import forecast, allocate, labor_cost, is_trading

def week_profit(hist, p, days, z, inv0=0, nxt=None):
    fc = forecast({d: v for d, v in hist.items() if d < days[0]}, p, days + (nxt or []), z)
    target = {d: fc[d][1] for d in days}
    look = {d: fc[d][1] for d in (nxt or [])}
    jobs, _ = allocate(p, days, target, inv0 // 1000, look)
    inv, profit, stock, sold_t, dem_t = inv0, 0, 0, 0, 0
    mat_unit = sum(q * CFG['mat_unit'][m] for m, q in CFG['bom'][p].items())
    for d in days:
        n = jobs[d]
        profit -= labor_cost(p, dow_of(d), n) + n * 1000 * mat_unit
        inv += n * 1000
        dem = hist.get(d, 0) if (p == 'P2' or is_trading(d)) else 0
        sold = min(inv, dem); inv -= sold
        profit += sold * CFG['price'][p] - (dem - sold) * CFG['stockout'] - inv * CFG['inv_cost']
        stock += dem - sold; sold_t += sold; dem_t += dem
    return profit, inv, stock, sold_t, dem_t, jobs

if __name__ == '__main__':
    hist = load_demand('data')
    start, end = pd.Timestamp('2025-07-06'), pd.Timestamp('2026-09-12')   # Sundays (62 weeks; z=0.4 chosen on this window)
    sundays = [d for d in pd.date_range(start, end, freq='W-SUN')]
    for p in ['P1', 'P2']:
        print(f'\n=== {p} ===  z:  profit/week (M$)   stockout%   PFR')
        for z in [0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.3, 1.6]:
            tot, inv, st, sd, dm, prod = 0, 0, 0, 0, 0, 0
            for s in sundays:
                days = [s + pd.Timedelta(days=i) for i in range(7)]
                nxt = [s + pd.Timedelta(days=7 + i) for i in range(2)]
                pr, inv, a, b, c, jobs = week_profit(hist[p], p, days, z, inv, nxt)
                tot += pr; st += a; sd += b; dm += c; prod += sum(jobs.values()) * 1000
            print(f'  z={z:<4} {tot/len(sundays)/1e6:8.2f}   {100*st/dm:5.2f}%   {prod/dm:.3f}')
