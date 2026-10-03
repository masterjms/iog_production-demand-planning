"""Permutation flow-shop makespan + NEH / iterated-greedy optimiser.

Processing time tables: ptt/t_500_20_<dow>.csv (P1), ptt/t2_500_20_<dow>.csv (P2).
Job IDs are always 1..n (the official scheduling_lib reads nrows=n from the top).
"""
import numpy as np, pandas as pd, random, os, time

DOW = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
HERE = os.path.dirname(os.path.abspath(__file__))


def load_ptt(product, dow, n):
    prefix = 't' if product == 'P1' else 't2'
    df = pd.read_csv(f'{HERE}/ptt/{prefix}_500_20_{dow}.csv', index_col='JobID', nrows=n)
    return df.values.astype(np.int64)  # shape (n, m), row i = job i+1


def makespan(P, seq):
    """seq: list of 0-based job indices. Standard permutation flow shop recursion."""
    m = P.shape[1]
    c = np.zeros(m, dtype=np.int64)
    for j in seq:
        row = P[j]
        c[0] += row[0]
        for k in range(1, m):
            c[k] = max(c[k], c[k - 1]) + row[k]
    return int(c[-1])


def spt(P):
    return list(np.argsort(P.sum(axis=1), kind='stable'))


def _insert_best(P, seq, job):
    """Try inserting job at every position (Taillard acceleration). Returns (seq, makespan)."""
    n, m = len(seq), P.shape[1]
    e = np.zeros((n + 1, m), dtype=np.int64)          # heads
    for i in range(1, n + 1):
        row = P[seq[i - 1]]
        e[i, 0] = e[i - 1, 0] + row[0]
        for k in range(1, m):
            e[i, k] = max(e[i - 1, k], e[i, k - 1]) + row[k]
    q = np.zeros((n + 2, m), dtype=np.int64)          # tails
    for i in range(n, 0, -1):
        row = P[seq[i - 1]]
        q[i, m - 1] = q[i + 1, m - 1] + row[m - 1]
        for k in range(m - 2, -1, -1):
            q[i, k] = max(q[i + 1, k], q[i, k + 1]) + row[k]
    rowj = P[job]
    best_pos, best_ms = 0, None
    f = np.empty(m, dtype=np.int64)
    for pos in range(n + 1):
        f[0] = e[pos, 0] + rowj[0]
        for k in range(1, m):
            f[k] = max(f[k - 1], e[pos, k]) + rowj[k]
        ms = int(np.max(f + q[pos + 1]))
        if best_ms is None or ms < best_ms:
            best_ms, best_pos = ms, pos
    return seq[:best_pos] + [job] + seq[best_pos:], best_ms


def neh(P):
    order = list(np.argsort(-P.sum(axis=1), kind='stable'))
    seq = [order[0]]
    for job in order[1:]:
        seq, _ = _insert_best(P, seq, job)
    return seq


def iterated_greedy(P, seq=None, d=4, seconds=30, seed=0, T=0.4):
    """Ruiz & Stuetzle iterated greedy with temperature acceptance."""
    rng = random.Random(seed)
    if seq is None:
        seq = neh(P)
    cur, cur_ms = seq[:], makespan(P, seq)
    best, best_ms = cur[:], cur_ms
    temp = T * P.sum() / (len(seq) * P.shape[1] * 10)
    t0 = time.time()
    while time.time() - t0 < seconds:
        removed = rng.sample(cur, d)
        partial = [j for j in cur if j not in removed]
        for job in removed:
            partial, ms = _insert_best(P, partial, job)
        improved = True
        while improved:
            improved = False
            for job in list(partial):
                p2 = [j for j in partial if j != job]
                p2, ms2 = _insert_best(P, p2, job)
                if ms2 < ms:
                    partial, ms, improved = p2, ms2, True
        if ms < cur_ms or rng.random() < np.exp(-(ms - cur_ms) / max(temp, 1e-9)):
            cur, cur_ms = partial, ms
            if ms < best_ms:
                best, best_ms = partial[:], ms
    return best, best_ms


def optimise(product, dow, n, seconds=30, seed=0):
    P = load_ptt(product, dow, n)
    s = spt(P)
    s_ms = makespan(P, s)
    seq, ms = iterated_greedy(P, seconds=seconds, seed=seed)
    return {'spt': s_ms, 'opt': ms, 'seq': [j + 1 for j in seq]}


if __name__ == '__main__':
    import sys
    product, dow, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    secs = float(sys.argv[4]) if len(sys.argv) > 4 else 30
    r = optimise(product, dow, n, secs)
    print(f'{product} {dow} n={n}: SPT={r["spt"]}  OPT={r["opt"]}  ({100*(1-r["opt"]/r["spt"]):.1f}% shorter)')
    print(','.join(map(str, r['seq'])))
