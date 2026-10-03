"""Nightly job (Windows Task Scheduler, 21:30): pick the active round by date, run the virtual daily check,
append the report to logs/daily_YYYY-MM-DD.txt and logs/latest.txt."""
import datetime as dt, io, os, sys, contextlib, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
ROUNDS = [('R2602A', '2026-09-13', '2026-09-25'), ('R2602B', '2026-09-27', '2026-10-16'), ('R2602C', '2026-11-01', '2026-12-04')]
today = dt.date.today().isoformat()
os.makedirs('logs', exist_ok=True)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    print(f'=== daily_run {dt.datetime.now():%Y-%m-%d %H:%M} ===')
    active = [r for r in ROUNDS if r[1] <= today <= r[2]] or [r for r in ROUNDS if r[1] > today][:1] or ROUNDS[-1:]
    rid, start, end = active[0]
    print('round', rid, start, end)
    try:
        import daily_check
        daily_check.run(rid, start, end, 'DKU/26_DKU_GMG', fetch=True)
    except Exception:
        traceback.print_exc()
out = buf.getvalue()
open(f'logs/daily_{today}.txt', 'w', encoding='utf-8').write(out)
open('logs/latest.txt', 'w', encoding='utf-8').write(out)
print(out)
