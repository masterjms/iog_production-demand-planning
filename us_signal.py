"""P1 level shift from the US session that closed after the last Samsung close (MU, SOX, EWY daily returns).
The US Friday session ends Sat 06:00 KST, before the Saturday 19:30 deadline, so the weekly plan can use it.
Samsung is a random walk, so a better first-day estimate moves the whole week's level.
Fit: rolling OLS over the last 750 KRX days, Samsung log return(t) ~ returns of the last US session before t.
5y check (2021-11..2026-11): Monday corr MU 0.51, SOX 0.40, EWY 0.36. Backtest (backtest.week_profit, P1, z 0.3):
62 weeks +0.73M/week, 202 weeks +0.33M, R2602B~C 9 weeks +0.69M (bt_us_signal.py); weekly win rate 44-67%,
62-week mean not significant per week (carry-over noise), the signal itself is (n=1218).
Data: python fetch_us.py -> data/us/{MU,SOX,EWY}.json. Missing or stale files -> shift 0 (planner falls back to naive)."""
import os, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
TICKERS = ['MU', 'SOX', 'EWY']
FIT_DAYS, R2_DAYS = 750, 250
K = 1.0           # shrink factor on the predicted return (0.5 = conservative)
CAP = 0.05        # clip the predicted return to +-5%
_us = None


def load_us(path=None):
    global _us
    if _us is None:
        _us = {}
        for k in TICKERS:
            f = f'{path or HERE + "/data/us"}/{k}.json'
            if not os.path.exists(f): _us = {}; break
            d = json.load(open(f))['chart']['result'][0]
            t = pd.to_datetime(np.array(d['timestamp']) + d['meta']['gmtoffset'], unit='s').normalize()
            _us[k] = np.log(pd.Series(d['indicators']['quote'][0]['close'], index=t).dropna()).diff().dropna()
    return _us


def _session(after, before):
    """Returns of the last US session with after <= date < before (all tickers), else None."""
    out = []
    for ru in load_us().values():
        j = np.searchsorted(ru.index.values, np.datetime64(pd.Timestamp(before))) - 1
        if j < 0 or ru.index[j] < pd.Timestamp(after): return None
        out.append(ru.iloc[j])
    return np.array(out)


def p1_shift(hist, first_day):
    """(mu, r2): predicted log return from the last close in hist to the first trading day `first_day`, and the
    out-of-fit R^2 used to shrink the day-1 sigma. (0, 0) when no US session has closed since the last close."""
    if not load_us(): return 0.0, 0.0
    dates = sorted(hist); last = dates[-1]
    x = _session(last, first_day)
    if x is None: return 0.0, 0.0
    lv = np.log(np.array([hist[d] for d in dates], dtype=float))
    X, y = [], []
    for i in range(max(1, len(dates) - FIT_DAYS), len(dates)):
        f = _session(dates[i - 1], dates[i])
        if f is not None: X.append(f); y.append(lv[i] - lv[i - 1])
    if len(y) < 200: return 0.0, 0.0
    X = np.c_[np.ones(len(y)), np.array(X)]; y = np.array(y)
    b = np.linalg.lstsq(X, y, rcond=None)[0]; res = (y - X @ b)[-R2_DAYS:]
    r2 = max(0.0, 1 - res.var() / y[-R2_DAYS:].var())
    return float(np.clip(K * (b[0] + x @ b[1:]), -CAP, CAP)), r2
