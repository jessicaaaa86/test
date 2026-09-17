# 선사 스케줄 vs 터미널 접안 스케줄 비교

수입팀에서 선사별로 공지하는 선박 스케줄과, 실제 터미널 접안(예정) 스케줄이
서로 어긋나는 문제를 해결하기 위한 프로젝트입니다. 선사 사이트의 스케줄보다
터미널의 실제 접안 스케줄이 더 정확하다는 전제 하에, 선박별로 두 스케줄을
나란히 비교할 수 있게 합니다. 인천을 시작으로 부산(북항/신항) 등으로 확장했습니다.

## 데이터 소스

**터미널 접안 스케줄 (기준 데이터)**
- 인천: [scrapers/icon_terminal.py](scrapers/icon_terminal.py) — 인천항만공사(IPA)의
  [iCON 통합정보](https://scon.icpa.or.kr/main.do?menuKey=19) "선석배정현황(텍스트)"을
  스크래핑. 로그인 불필요, 정부기관 공식 데이터. 인천 5개 터미널(선광/SNCT, 한진/HJIT,
  E1CT, 인천/ICT, 국제여객부두) 전체의 접안(예정)일시·출항(예정)일시·선사명을 제공.
- 그 외 항구(부산 북항/신항 등): [scrapers/tradlinx.py](scrapers/tradlinx.py)의
  `fetch_berthplan()` — 아래 참고.

**선사 공지 스케줄**
- 전 항구: [scrapers/tradlinx.py](scrapers/tradlinx.py)의 `fetch_carrier_schedules_for_port()`
  — 아래 참고.

### Tradlinx 관련 중요 사항

[scrapers/tradlinx.py](scrapers/tradlinx.py)는 물류 플랫폼 트레드링스(tradlinx.com)의
웹페이지가 내부적으로 쓰는 API(`api.tradlinx.com`)를 그대로 이용합니다:
- `/terminal`: 전국 컨테이너 터미널 목록 (부산 북항/신항 포함 27개)
- `/berthplan`: 전국 터미널 실시간 접안계획 (터미널 접안 스케줄)
- `/fclschedule?depPort=X&arrPort=Y`: 출발항-도착항 구간의 선사 공지 스케줄
  (KMTC, CK Line, 흥아라인, 동영해운 등 다수 선사 포함을 확인함)

로그인 없이 고정 헤더(`tx-clientid: tradlinx`)만으로 호출되지만, **이건 트레드링스가
공식적으로 공개한 오픈 API가 아니라 자사 웹페이지용 내부 API입니다.** 예고 없이
바뀌거나 막힐 수 있고, 트레드링스는 이 데이터를 유료 서비스로도 판매하는 민간
업체이므로 상시 자동 수집이 트레드링스 이용약관과 상충할 수 있습니다. 사내에서
지속적으로 쓸 경우 트레드링스와 정식 이용 관계를 맺는 것을 고려하세요.

`fclschedule`은 출발항을 지정해야만 조회되므로, [scrapers/tradlinx.py](scrapers/tradlinx.py)의
`INTRA_ASIA_ORIGIN_PORTS`에 있는 주요 근해 항구들을 출발항 후보로 순회하며 도착항과
조합해 조회합니다. 특정 선사/항로가 안 잡히면 이 목록에 항구를 추가하면 됩니다.

## 구성

- [db.py](db.py): SQLite 저장소 (`schedule.db`, git에는 포함 안 됨). `terminal_calls`
  (터미널 접안 스케줄, 항구별로 구분)와 `carrier_schedules`(선사 공지 스케줄)를 저장.
- [match.py](match.py): 선박명 기준으로 두 데이터를 매칭하고 ETA 차이를 계산합니다.
  같은 선박이 몇 주 간격으로 반복 기항하거나 여러 선사가 공동 배선(joint service)을
  공지하는 경우가 흔해서, 터미널 ETA와 며칠 이상 차이나는 후보는 다른 항차로 보고
  매칭에서 제외합니다 (`MAX_CANDIDATE_ETA_GAP_DAYS`). 남은 후보 중 항차 일치 > 선사명
  일치 > ETA가 가장 가까운 순으로 고르고, 6시간 이상 차이나면 화면에서 강조합니다.
- [app.py](app.py): Flask 대시보드. `/`에서 항구별로 필터링 가능한 비교 표를 보여주고,
  "지금 새로고침" 버튼으로 iCON + Tradlinx를 다시 스크래핑합니다.
- 자동으로 못 찾은 선사 ETA는 표 오른쪽에서 담당자가 직접 입력할 수 있습니다
  (`source=MANUAL`로 표시됨).
- [scrapers/carriers/base.py](scrapers/carriers/base.py): (참고용, 현재 미사용) 선사
  사이트를 개별적으로 직접 스크래핑하려던 시도의 흔적. KMTC는 Akamai 봇 차단, 동영해운
  자체 사이트는 로그인 필요, 흥아라인 자체 사이트는 서버 오류 상태라 개별 스크래핑을
  포기하고 Tradlinx로 전환했습니다.

## 실행 방법

```bash
pip install -r requirements.txt
python app.py
```

브라우저에서 http://localhost:5000 접속.

## 다음 단계

1. 주기적 자동 새로고침(스케줄러) 추가
2. 트레드링스 API 의존에 대한 사내 검토 (정식 이용 관계 필요 여부)
3. 필요한 항구/터미널이 더 있으면 `app.py`의 `TRACKED_PORTS`에 추가
