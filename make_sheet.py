"""plans/<round>_<week>.json -> 대시보드 입력 시트(.txt). 순서는 공식 scheduling_lib로 재검증.
사용: python make_sheet.py plans/R2602C_2026-11-01.json"""
import json, sys, pandas as pd, warnings; warnings.filterwarnings('ignore')
import scheduling_lib as sl
p=json.load(open(sys.argv[1])); out=[f"# {p['round']} 입력 시트 (주 {p['week'][0]}~{p['week'][-1]}, 생성 asof {p['asof']}, z={p['z']})",'',
 '## Demand (예측 원값, 안전마진 X)','날짜 | P1 | P2']
for d in p['week']: out.append(f"{d} | {p['forecast']['P1'][d]} | {p['forecast']['P2'][d]}")
out+=['','## Production (AUTO OFF / 생산하는 칸은 ○ Job sequence 선택 후 붙여넣기 / 0 Job 칸은 Job qty 0)','']
ok=True
for d in p['week']:
    for prod in ['P1','P2']:
        n=p['jobs'][d][prod]
        if n==0: out.append(f'[{d} {prod}] 0 Job'); continue
        s=p['sequences'][f'{d}_{prod}']; seq=s['seq']; valid=sorted(seq)==list(range(1,n+1))
        pre='t' if prod=='P1' else 't2'; dow=pd.Timestamp(d).strftime('%a').lower()
        ms=int(sl.build_schedule(seq, pd.read_csv(f'ptt/{pre}_500_20_{dow}.csv',index_col='JobID',nrows=n)).iloc[-1,-1])
        ok&=valid and ms==s['opt']
        out.append(f'[{d} {prod}] {n} Job | 예상 makespan {ms} ({ms//100}h, SPT {s["spt"]//100}h) | 검증 {"OK" if valid and ms==s["opt"] else "FAIL"}'); out.append(','.join(map(str,seq))); out.append('')
out+=['## Material (그날 칸에만 입력, 19:30 전, AUTO OFF 확인)']
for pl,m,q,arr,u in sorted(p['orders']): out.append(f'{pl} | {m} | {"Urgent" if u else "Normal"} | {q} | 도착 {arr}')
if p['warnings']: out+=['','## WARNINGS']+[f'- {w}' for w in p['warnings']]
dst=sys.argv[1].replace('.json','_INPUT.txt'); open(dst,'w',encoding='utf-8').write('\n'.join(out)); print('all sequences verified:',ok,'->',dst)
