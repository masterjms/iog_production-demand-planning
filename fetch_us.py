"""Download 5y daily closes of MU, ^SOX, EWY (Yahoo chart API) into data/us/ for us_signal.py.
Run on Saturday after 06:00 KST (US Friday session closed) before planner.py."""
import os, json, requests
HERE = os.path.dirname(os.path.abspath(__file__))
SYMBOLS = {'MU': 'MU', 'SOX': '^SOX', 'EWY': 'EWY'}
os.makedirs(f'{HERE}/data/us', exist_ok=True)
for name, sym in SYMBOLS.items():
    r = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}', params={'range': '5y', 'interval': '1d'},
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
    r.raise_for_status(); d = r.json()
    json.dump(d, open(f'{HERE}/data/us/{name}.json', 'w'))
    res = d['chart']['result'][0]; print(name, len(res['timestamp']), 'bars, last close', res['indicators']['quote'][0]['close'][-1])
