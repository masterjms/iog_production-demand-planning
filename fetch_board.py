"""Fetch public team boards (no login) and parse tables into CSV."""
import re, sys, pandas as pd, io, requests
BASE='http://play.ioground.kr:5005'
def tables(url):
    h=requests.get(url,timeout=30).text
    try: return pd.read_html(io.StringIO(h))
    except ValueError: return []
def fetch(team='DKU/26_DKU_GMG', rnd='R2602A', out='data'):
    import os; os.makedirs(out,exist_ok=True)
    res={}
    for kind in ['ledger','production','material','demand','sales']:
        ts=tables(f'{BASE}/plans_{kind}/board/{team}/{rnd}')
        for i,t in enumerate(ts):
            t.to_csv(f'{out}/{kind}_{i}.csv',index=False)
        res[kind]=ts
    return res
if __name__=='__main__':
    r=fetch(*(sys.argv[1:3] if len(sys.argv)>2 else []))
    for k,v in r.items():
        print(k,[t.shape for t in v])
