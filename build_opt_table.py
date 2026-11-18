"""Add an 'opt' column to ms_table.csv: P1 makespans from the fast solver (one 6 s run per cell, 10 in parallel).
The NEH column is ~3-5% too long for P1, which misplaces the 70 h line used by the planner. P2 keeps NEH (= lower bound)."""
import json, subprocess, sys, pandas as pd
from concurrent.futures import ThreadPoolExecutor
from flowshop import HERE, load_ptt, makespan
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 6
t = pd.read_csv('ms_table.csv'); cells = [(r.dow, int(r.n)) for r in t.itertuples() if r.product == 'P1' and r.dow in ('mon', 'tue', 'wed', 'thu', 'fri') and r.n <= 300]
def run(c):
    dow, n = c
    o = json.loads(subprocess.run(['node', f'{HERE}/fs_solver.js', f'{HERE}/ptt/t_500_20_{dow}.csv', str(n), str(secs), '1', '4', '0.4', 'rs:ts'], capture_output=True, text=True, check=True).stdout)
    assert makespan(load_ptt('P1', dow, n), [j - 1 for j in o['seq']]) == o['ms']; return c, o['ms']
with ThreadPoolExecutor(10) as ex: res = dict(ex.map(run, cells))
t['opt'] = [res.get((r.dow, int(r.n))) if r.product == 'P1' else None for r in t.itertuples()]
t.to_csv('ms_table.csv', index=False); print('cells', len(res)); print(t[(t['product'] == 'P1') & (t.dow == 'mon') & t.n.isin([85, 100, 110, 115, 120, 200])].to_string(index=False))
