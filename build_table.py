import pandas as pd, sys
from flowshop import *
rows=[]
for prod in ['P1','P2']:
    for dow in DOW:
        for n in list(range(5,501,5)):
            P=load_ptt(prod,dow,n); s=makespan(P,spt(P)); q=neh(P); nm=makespan(P,q)
            rows.append(dict(product=prod,dow=dow,n=n,spt=s,neh=nm))
        pd.DataFrame(rows).to_csv('ms_table.csv',index=False); print(prod,dow,flush=True)
