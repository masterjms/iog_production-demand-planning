"""Fast sequence optimiser: runs fs_solver.js (node) on several cores with different seeds, keeps the best ever found
per (product, weekday, n) in seqlib/ and verifies every result with the Python makespan (same recursion as scheduling_lib).
Falls back to the pure-Python iterated greedy when node is not installed.
  python fastshop.py P1 mon 212 60        -> best sequence after 60 s on 10 workers"""
import json, os, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from flowshop import load_ptt, makespan, neh, iterated_greedy, HERE

LIB = f'{HERE}/seqlib'
CONFIGS = [(4, 0.4, 'rs:ts'), (4, 0.2, 'rs:ts'), (3, 0.4, 'rs:ts'), (5, 0.4, 'rs:ts'), (4, 0.6, 'rs:ts'), (2, 0.4, 'rs:ts'), (6, 0.4, 'rs:ts'), (4, 0.4, 'rs')]   # :ts = random tie-break + sideways moves (measured -0.2% vs plain)


def lower_bound(P):
    """Machine-based bound: for each machine, shortest head + total load + shortest tail."""
    n, m = P.shape; best = int(P.sum(axis=1).max())
    for k in range(m):
        head = int(P[:, :k].sum(axis=1).min()) if k else 0
        tail = int(P[:, k + 1:].sum(axis=1).min()) if k < m - 1 else 0
        best = max(best, head + int(P[:, k].sum()) + tail)
    return best


def lib_get(product, dow, n):
    f = f'{LIB}/{product}_{dow}_{n}.json'
    return json.load(open(f)) if os.path.exists(f) else None


def lib_put(product, dow, n, seq, ms):
    os.makedirs(LIB, exist_ok=True); old = lib_get(product, dow, n)
    if old is None or ms < old['ms']:
        json.dump({'ms': int(ms), 'seq': [int(j) for j in seq]}, open(f'{LIB}/{product}_{dow}_{n}.json', 'w'))


def solve(product, dow, n, seconds=60, workers=10, init=None, use_lib=True, seed0=0, round_secs=60):
    """Returns (seq 1-based, makespan). Multi-start over several cores, time split into rounds (see `run`). The best
    sequence ever found for (product, weekday, n) is kept in seqlib/, so repeated calls only ever improve."""
    P = load_ptt(product, dow, n)
    best = lib_get(product, dow, n) if use_lib else None
    if best and makespan(P, [j - 1 for j in best['seq']]) != best['ms']: best = None
    lb = lower_bound(P)
    if best and best['ms'] <= lb: return best['seq'], best['ms']
    gbest = (best['ms'], best['seq']) if best else ((makespan(P, [j - 1 for j in init]), list(init)) if init and len(init) == n else None)
    if shutil.which('node') is None:                                  # portable fallback
        q = [j - 1 for j in gbest[1]] if gbest else neh(P)
        seq, ms = iterated_greedy(P, q, seconds=seconds); cand = [(ms, [j + 1 for j in seq])] + ([gbest] if gbest else [])
        gbest = min(cand, key=lambda r: r[0])
    else:
        pre = 't' if product == 'P1' else 't2'; csv = f'{HERE}/ptt/{pre}_500_20_{dow}.csv'
        rounds = max(1, int(round(seconds / round_secs))); own = [None] * workers
        def run(a):
            i, r = a; d, T, v = CONFIGS[(i + r) % len(CONFIGS)]
            cmd = ['node', f'{HERE}/fs_solver.js', csv, str(n), str(seconds / rounds), str(seed0 + 1 + i + 1000 * r), str(d), str(T), v]
            # round 0: every worker explores its own basin from a randomised NEH start (worker 0 polishes the library best);
            # later rounds: a third continue from the global best, a third from their own best, a third explore afresh
            if r == 0: start = gbest if (i == 0 and gbest) else 'rand'
            else: start = [gbest, own[i], 'rand'][i % 3] or 'rand'
            cmd.append(start if start == 'rand' else ','.join(map(str, start[1])))
            o = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
            return i, (o['ms'], o['seq'])
        for r in range(rounds):
            with ThreadPoolExecutor(workers) as ex: out = list(ex.map(run, [(i, r) for i in range(workers)]))
            for i, res in out:
                if own[i] is None or res[0] < own[i][0]: own[i] = res
            cand = [o for o in own if o] + ([gbest] if gbest else [])
            gbest = min(cand, key=lambda x: x[0])
            if gbest[0] <= lb: break
    ms, seq = gbest
    assert sorted(seq) == list(range(1, n + 1)) and makespan(P, [j - 1 for j in seq]) == ms, 'verification failed'
    if use_lib: lib_put(product, dow, n, seq, ms)
    return seq, ms


if __name__ == '__main__':
    product, dow, n = sys.argv[1], sys.argv[2], int(sys.argv[3]); secs = float(sys.argv[4]) if len(sys.argv) > 4 else 60
    seq, ms = solve(product, dow, n, secs)
    print(f'{product} {dow} n={n}: makespan {ms} ({ms // 100}h)  lower bound {lower_bound(load_ptt(product, dow, n))}')
    print(','.join(map(str, seq)))
