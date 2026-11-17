"""Fetch every team's public ledger/production/material boards and build a cost breakdown (final-Balance view).
python team_compare.py fetch   -> data_all/<team>_{ledger,production,material0,material1}.csv
python team_compare.py         -> prints the comparison from the cached files"""
import sys, os, re, io, requests, pandas as pd
from concurrent.futures import ThreadPoolExecutor
BASE, RND, OUT = 'http://play.ioground.kr:5005', 'R2602C', 'data_all'
def teams():
    h = requests.get(f'{BASE}/{RND}', timeout=30).text
    return re.findall(rf"/plans_demand/board/([^/]+)/([^/]+)/{RND}", h)
def get(t):
    u, n = t
    for kind in ['ledger', 'production', 'material']:
        try: ts = pd.read_html(io.StringIO(requests.get(f'{BASE}/plans_{kind}/board/{u}/{n}/{RND}', timeout=60).text))
        except ValueError: ts = []
        for i, x in enumerate(ts): x.to_csv(f'{OUT}/{n}_{kind}{i}.csv', index=False)
    return n
if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'fetch':
    os.makedirs(OUT, exist_ok=True); T = teams()
    with ThreadPoolExecutor(8) as ex: done = list(ex.map(get, T))
    print('fetched', len(done))

def money(s): return pd.to_numeric(s.astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce').fillna(0)
def load():
    rows = []
    for f in sorted(os.listdir(OUT)):
        if f.endswith('_ledger0.csv'):
            d = pd.read_csv(f'{OUT}/{f}'); d['team'] = f[:-len('_ledger0.csv')]
            d['Revenue'] = money(d.Revenue); d['Expense'] = money(d.Expense); rows.append(d)
    return pd.concat(rows)
def cat(a):
    if a.startswith('SALES_INVENTORY'): return 'fg_hold'
    if a.startswith('MATERIAL_INVENTORY'): return 'mat_hold'
    if a.startswith('SALES_'): return 'rev_' + a[-2:]
    if a.startswith('STOCKOUT'): return 'stockout'
    if a.startswith('PRODUCTION_P'): return 'prod_' + a[-2:]
    if a.startswith('MATERIAL_PURCHASE'): return 'mat_urgent' if a.endswith('URGENT') else 'mat_normal'
    return 'other'
PRICE = {'M1': 30, 'M2': 25, 'M3': 50}
def summary():
    L = load(); L['cat'] = L.Action.map(cat); L['net'] = L.Revenue - L.Expense
    S = L.pivot_table(index='team', columns='cat', values='net', aggfunc='sum', fill_value=0)
    S['net'] = L.groupby('team').net.sum()
    mv = {}
    for t in S.index:
        try:
            m = pd.read_csv(f'{OUT}/{t}_material0.csv'); mv[t] = sum(PRICE[r['Material type']] * r['Current level'] for _, r in m.iterrows())
        except Exception: mv[t] = 0
    S['mat_stock'] = pd.Series(mv); S['adj'] = S.net + S.mat_stock
    D = L.pivot_table(index='Date', columns='team', values='net', aggfunc='sum', fill_value=0).cumsum()
    R = D.rank(axis=1, ascending=False, method='min')
    return L, S, D, R
if __name__ == '__main__' and len(sys.argv) == 1:
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
    L, S, D, R = summary()
    S['rank'] = S.net.rank(ascending=False, method='min'); S['adj_rank'] = S.adj.rank(ascending=False, method='min')
    cols = ['rank', 'net', 'adj_rank', 'adj', 'mat_stock', 'rev_P1', 'rev_P2', 'stockout', 'prod_P1', 'prod_P2', 'mat_normal', 'mat_urgent', 'fg_hold', 'mat_hold']
    print((S.sort_values('net', ascending=False)[cols].head(16) / 1e6).round(1).assign(rank=lambda x: (x['rank'] * 1e6).astype(int), adj_rank=lambda x: (x.adj_rank * 1e6).astype(int)).to_string())
    print('\nrank by day (last 8 days) for top 12 + biggest climbers')
    last = R.index[-1]; chg = (R.loc[R.index[-6]] - R.loc[last]).sort_values(ascending=False)
    show = list(S.sort_values('net', ascending=False).head(12).index) + [t for t in chg.head(6).index]
    print(R[list(dict.fromkeys(show))].tail(8).astype(int).T.to_string())
    print('\nbiggest climbers over last 5 days:', chg.head(8).to_dict())
