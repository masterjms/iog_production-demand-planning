// Permutation flow-shop makespan optimiser: NEH + iterated greedy (Ruiz & Stuetzle) with Taillard acceleration,
// optional local search on the partial solution (Dubois-Lacoste et al. 2017, "IG_ALL").
// usage: node fs_solver.js <ptt.csv> <n> <seconds> <seed> <d> <T> <variant: rs|all> [init: comma-separated 1-based ids]
// prints one JSON line {ms, iters, seq}
'use strict';
const fs = require('fs');
const [, , file, nS, secS, seedS, dS, TS, variant, init] = process.argv;
const n = +nS, seconds = +secS, D = +dS, TT = +TS;
const [VAR, FLAGS = ''] = (variant || 'rs').split(':'), TIE = FLAGS.includes('t'), SIDE = FLAGS.includes('s');
const lines = fs.readFileSync(file, 'utf8').trim().split(/\r?\n/);
const head = lines[0].split(','), idc = head.indexOf('JobID');
const m = head.length - 1;
const P = new Int32Array(n * m);
for (let i = 0; i < n; i++) { const c = lines[i + 1].split(','); let k = 0; for (let x = 0; x < c.length; x++) if (x !== idc) P[i * m + k++] = +c[x]; }
let s = (+seedS * 2654435761 + 12345) >>> 0;
function rnd() { s |= 0; s = s + 0x6D2B79F5 | 0; let t = Math.imul(s ^ s >>> 15, 1 | s); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }
const E = new Int32Array((n + 2) * m), Q = new Int32Array((n + 2) * m), F = new Int32Array(m);
function makespan(seq, L) {
  const c = new Int32Array(m);
  for (let i = 0; i < L; i++) { const b = seq[i] * m; c[0] += P[b]; for (let k = 1; k < m; k++) c[k] = (c[k] > c[k - 1] ? c[k] : c[k - 1]) + P[b + k]; }
  return c[m - 1];
}
// best position (0..L) to insert job into seq[0..L-1]; returns [pos, ms]
let bpos = 0, bms = 0;
function bestInsert(seq, L, job) {
  for (let k = 0; k < m; k++) { E[k] = 0; Q[L * m + k] = 0; }
  for (let i = 1; i <= L; i++) {
    const b = seq[i - 1] * m, r = i * m, pr = r - m;
    E[r] = E[pr] + P[b];
    for (let k = 1; k < m; k++) { const a = E[pr + k], c = E[r + k - 1]; E[r + k] = (a > c ? a : c) + P[b + k]; }
  }
  for (let i = L - 1; i >= 0; i--) {
    const b = seq[i] * m, r = i * m, nx = r + m;
    Q[r + m - 1] = Q[nx + m - 1] + P[b + m - 1];
    for (let k = m - 2; k >= 0; k--) { const a = Q[nx + k], c = Q[r + k + 1]; Q[r + k] = (a > c ? a : c) + P[b + k]; }
  }
  const jb = job * m; let best = 2147483647, bp = 0, ties = 1;
  for (let pos = 0; pos <= L; pos++) {
    const r = pos * m; let f = E[r] + P[jb], mx = f + Q[r];
    for (let k = 1; k < m; k++) { const a = E[r + k]; f = (f > a ? f : a) + P[jb + k]; const v = f + Q[r + k]; if (v > mx) mx = v; }
    if (mx < best) { best = mx; bp = pos; ties = 1; }
    else if (TIE && mx === best && rnd() * (++ties) < 1) bp = pos;
  }
  bpos = bp; bms = best;
}
function insertAt(seq, L, pos, job) { for (let i = L; i > pos; i--) seq[i] = seq[i - 1]; seq[pos] = job; }
function removeAt(seq, L, pos) { for (let i = pos; i < L - 1; i++) seq[i] = seq[i + 1]; }
const ord = new Int32Array(n);
// insertion local search until no job can be moved to a better position; returns makespan
function localSearch(seq, L, ms) {
  let improved = true;
  while (improved) {
    improved = false;
    for (let i = 0; i < L; i++) ord[i] = seq[i];
    for (let i = L - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); const t = ord[i]; ord[i] = ord[j]; ord[j] = t; }
    for (let x = 0; x < L; x++) {
      const job = ord[x]; let p = 0; while (seq[p] !== job) p++;
      removeAt(seq, L, p); bestInsert(seq, L - 1, job);
      if (bms < ms) { insertAt(seq, L - 1, bpos, job); ms = bms; improved = true; }
      else if (SIDE && bms === ms) insertAt(seq, L - 1, bpos, job);
      else insertAt(seq, L - 1, p, job);
    }
  }
  return ms;
}
function neh() {
  const tot = []; for (let j = 0; j < n; j++) { let t = 0; for (let k = 0; k < m; k++) t += P[j * m + k]; tot.push([t, j]); }
  if (init === 'rand') for (const t of tot) t[0] *= 1 + 0.5 * (rnd() - 0.5);        // randomised NEH order -> different basin per seed
  tot.sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  const seq = new Int32Array(n + 1); seq[0] = tot[0][1]; let L = 1;
  for (let i = 1; i < n; i++) { bestInsert(seq, L, tot[i][1]); insertAt(seq, L, bpos, tot[i][1]); L++; }
  return seq;
}
let cur = new Int32Array(n + 1);
if (init && init !== 'rand') {                                   // warm start: keep given order for jobs < n, insert the missing ones greedily
  const seen = new Uint8Array(n); let L = 0;
  for (const t of init.split(',')) { const j = +t - 1; if (j >= 0 && j < n && !seen[j]) { seen[j] = 1; cur[L++] = j; } }
  for (let j = 0; j < n; j++) if (!seen[j]) { bestInsert(cur, L, j); insertAt(cur, L, bpos, j); L++; }
} else cur = neh();
let curMs = localSearch(cur, n, makespan(cur, n));
let best = cur.slice(), bestMs = curMs, iters = 0;
let sumP = 0; for (let i = 0; i < n * m; i++) sumP += P[i];
const temp = TT * sumP / (n * m * 10);
const t0 = Date.now(), work = new Int32Array(n + 1), rem = new Int32Array(D);
while (Date.now() - t0 < seconds * 1000) {
  work.set(cur); let L = n;
  for (let x = 0; x < D; x++) { const p = Math.floor(rnd() * L); rem[x] = work[p]; removeAt(work, L, p); L--; }
  if (VAR === 'all') localSearch(work, L, makespan(work, L));
  let ms = 0;
  for (let x = 0; x < D; x++) { bestInsert(work, L, rem[x]); insertAt(work, L, bpos, rem[x]); L++; ms = bms; }
  ms = localSearch(work, n, ms);
  if (ms < curMs || rnd() < Math.exp(-(ms - curMs) / temp)) {
    cur.set(work); curMs = ms;
    if (ms < bestMs) { bestMs = ms; best = work.slice(); }
  }
  iters++;
}
if (makespan(best, n) !== bestMs) throw new Error('makespan mismatch');
console.log(JSON.stringify({ ms: bestMs, iters, seq: Array.from(best.slice(0, n), j => j + 1) }));
