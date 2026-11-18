"""Backtest of us_signal on/off with backtest.week_profit (P1). Usage: python bt_us_signal.py"""
import pandas as pd, numpy as np, planner, backtest
from sim import load_demand
hist = load_demand('data')
def run(start, end, z, on):
    planner.US_SIGNAL = on; tot = inv = st = dm = 0; wk = []
    for s in pd.date_range(start, end, freq='W-SUN'):
        days = [s + pd.Timedelta(days=i) for i in range(7)]; nxt = [s + pd.Timedelta(days=7 + i) for i in range(2)]
        pr, inv, a, b, c, jobs = backtest.week_profit(hist['P1'], 'P1', days, z, inv, nxt)
        tot += pr; st += a; dm += c; wk.append(pr)
    return tot / len(wk) / 1e6, 100 * st / dm, np.array(wk)
for lab, a, b in [('62 weeks', '2025-07-06', '2026-09-12'), ('202 weeks', '2023-01-01', '2026-11-08'), ('R2602B~C 9 weeks', '2026-09-13', '2026-11-08')]:
    for z in [0.2, 0.3, 0.4]:
        n, ns, wn = run(a, b, z, False); s, ss, ws = run(a, b, z, True); d = (ws - wn) / 1e6
        print(f'{lab:17s} z={z}: naive {n:.3f} ({ns:.2f}%)  us_signal {s:.3f} ({ss:.2f}%)  diff {s-n:+.3f}/week  win {np.mean(d>0):.0%}')
