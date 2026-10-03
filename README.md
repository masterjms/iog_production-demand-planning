# IOG 생산·수요·자재 계획 툴체인 (팀 26_DKU_GMG)

IOG(㈜K-Bottle) 대회용 도구 모음. 수요예측 → 생산량 결정 → P2 요일 배분 → Job 순서 최적화 → 자재 발주 달력까지 한 번에 만든다.
시뮬레이터는 실제 Ledger를 1달러 단위까지 재현한다(56/56 항목 일치).

## 설치 (처음 한 번)
```
git clone https://github.com/masterjms/iog_production-demand-planning.git
cd iog_production-demand-planning
pip install -r requirements.txt
```

## 매주 토요일 (19:30 마감 전) 주간계획 만들기
1. 최신 수요 데이터 받기 (16시 갱신 이후):
   ```
   python daily_check.py --round R2602B --start 2026-09-27 --end 2026-10-16
   ```
2. 주간계획 생성:
   ```
   python planner.py --asof 2026-10-10 --round R2602B --start 2026-09-27 --end 2026-10-16 --ig 30 \
      --mat '{"M1":..,"M2":..,"M3":..}' --inv '{"P1":..,"P2":..}' --pending '[["2026-10-12","M2",2182000,false]]'
   ```
   - `--asof` = 오늘(토요일). `--mat`/`--inv` = 대시보드의 현재 자재·완제품 재고, `--pending` = 도착 예정 주문.
   - 결과: `plans/<round>_<주시작일>.md` (Job 수, CUSTOM 순서, 자재 발주 달력).
3. 대시보드 입력 시 주의:
   - Production: 생산하는 칸은 **○ Job sequence 선택** 후 순서 붙여넣기. 0 Job인 칸은 Job qty 0.
   - Demand: 예측 원값(안전마진 X). P1은 증시 휴장일 0.
   - Material: AUTO **OFF**, 그날 칸에만 입력.
   - 입력 후 공개 게시판에서 Planned #Jobs, Algo=CUSTOM 확인.

## 매일
- Windows 작업 스케줄러가 21:30에 `daily_run.py` 실행 → `logs/latest.txt` (이 PC 전용 설정).
- 다른 PC에서는 `python daily_run.py` 를 직접 실행하면 된다.

## 파일
| 파일 | 역할 |
|---|---|
| flowshop.py | makespan 계산(공식 scheduling_lib와 동일) + NEH/IG 순서 최적화. `python flowshop.py P1 mon 260 30` |
| sim.py | Ledger 시뮬레이터 |
| planner.py | 주간 계획 생성 (예측→수량→P2 요일배분 DP→자재발주→순서) |
| backtest.py | 안전계수 z 튜닝 (현재 P1 0.4, P2 0.4) |
| daily_check.py / daily_run.py | 가상 라운드 결과 vs 실제 보드 비교, 데이터 갱신 |
| fetch_board.py | 공개 보드 수집 → data/ |
| ms_table.csv | 제품·요일·Job수별 NEH makespan 표 (build_table.py로 재생성, 약 20분) |
| ptt/ | 요일별 공정시간표 (t_=P1, t2_=P2) |
| scheduling_lib.py | 주최측 공식 채점 코드 (출처: github.com/Kahkim/kahkim) |

## 검증된 게임 규칙
- AUTO SPT = 1번 기계 시간 오름차순. 자재 부족 시 Job ID 1..k만 생산.
- 인건비 = ⌊makespan/100⌋시간 × $100k, 70시간 초과분은 $100k 추가.
- 자재 구매비는 도착일 청구, 도착 당일 사용 가능. 품절은 이월 없음(lost sales).
- 대체공휴일에도 증시 휴장(P1 수요 0). 2026: 10/5, 10/9 휴장.
