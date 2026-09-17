# -*- coding: utf-8 -*-
"""
트레드링스(Tradlinx) 내부 API를 이용한 선사 공지 스케줄 + 전국 터미널 접안계획 조회.

트레드링스(www.tradlinx.com)는 국내 최대 수출입 물류 플랫폼으로, 여러 선사의 공지
스케줄과 전국 컨테이너 터미널의 접안계획을 자체적으로 통합해서 제공한다. 이 모듈은
그 웹페이지가 내부적으로 호출하는 API(api.tradlinx.com)를 그대로 이용한다.

중요 - 사용 전 반드시 인지할 것:
- 이 API는 트레드링스가 공식적으로 공개/문서화한 오픈 API가 아니다. 로그인은 필요
  없지만(고정 헤더 tx-clientid: tradlinx만 있으면 호출됨) 어디까지나 자사 웹페이지용
  내부 엔드포인트이므로, 예고 없이 바뀌거나 막힐 수 있다.
- 트레드링스는 이 데이터를 유료 서비스로도 판매하는 민간 업체다. 이 데이터를
  상시/자동으로 긁어 쓰는 것이 트레드링스 이용약관과 상충할 수 있다는 점을
  인지하고, 사내에서 지속적으로 쓸 경우 트레드링스와 정식 이용 관계를 맺는 것도
  고려할 것.

제공하는 세 가지 조회:
- fetch_terminals(): 전국 컨테이너 터미널 목록/메타데이터 (부산 북항·신항 포함)
- fetch_berthplan(): 전국 터미널의 실시간 접안계획 (터미널 접안 스케줄 - ground truth)
- fetch_fcl_schedule(dep_port, arr_port): 출발항-도착항 구간의 선사 공지 스케줄
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests

API_BASE = "https://api.tradlinx.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "tx-clientid": "tradlinx",
    "Referer": "https://www.tradlinx.com/",
    "Accept": "application/json, text/plain, */*",
}

# 인천/부산 등 국내항과 실제로 항로가 연결되는 주요 근해 항구들.
# 선사 공지 스케줄(fclschedule)은 출발항-도착항 쌍으로만 조회할 수 있어서,
# 이 목록을 출발항 후보로 순회하며 도착항(예: 인천)과 조합해 조회한다.
# 조회 결과에 없는 선사가 있다면 이 목록에 해당 항구를 추가하면 된다.
INTRA_ASIA_ORIGIN_PORTS: dict[str, str] = {
    "CNSGH": "Shanghai",
    "CNTAO": "Qingdao",
    "CNNGB": "Ningbo",
    "CNDLC": "Dalian",
    "CNXNG": "Xingang(Tianjin)",
    "CNWEH": "Weihai",
    "CNYTI": "Yantai",
    "CNLYG": "Lianyungang",
    "CNRZH": "Rizhao",
    "CNSHK": "Shekou",
    "HKHKG": "Hong Kong",
    "TWKHH": "Kaohsiung",
    "JPOSA": "Osaka",
    "JPTYO": "Tokyo",
    "JPYOK": "Yokohama",
    "JPUKB": "Kobe",
    "JPHKT": "Hakata",
    "VNSGN": "Ho Chi Minh",
    "VNHPH": "Haiphong",
    "THLCH": "Laem Chabang",
    "THBKK": "Bangkok",
    "RUVVO": "Vladivostok",
}


def _parse_dtm(s: Optional[str]) -> Optional[str]:
    """'202609170200' -> ISO 8601 문자열. 값이 없거나 전부 0이면 None."""
    if not s or s == "000000000000":
        return None
    try:
        return datetime.strptime(s, "%Y%m%d%H%M").isoformat()
    except ValueError:
        return None


@dataclass
class BerthPlanCall:
    terminal: str
    terminal_nm: str
    port_cd: str
    port_nm: str
    vessel_call: str  # 항차
    vessel_nm: str
    berth_no: Optional[str]
    eta: Optional[str]      # 접안(예정)일시
    cutoff: Optional[str]   # 반입마감
    etd: Optional[str]      # 출항(예정)일시
    operator: Optional[str]  # 선사 코드 (짧은 코드, 예: HAS=흥아라인, PCS=동영해운)
    imo_no: Optional[str]


@dataclass
class FclScheduleCall:
    carrier_cd: str
    carrier_nm: str
    dep_port_cd: str
    dep_port_nm: str
    arr_port_cd: str
    arr_port_nm: str
    vessel_nm: str
    voyage: str
    dep_etd: Optional[str]
    arr_eta: Optional[str]
    cargo_close: Optional[str]
    line_plan_url: Optional[str]


def fetch_terminals(session: Optional[requests.Session] = None, timeout: int = 20) -> list[dict]:
    sess = session or requests.Session()
    r = sess.get(f"{API_BASE}/terminal", headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json().get("data") or []


def fetch_berthplan(session: Optional[requests.Session] = None, timeout: int = 30) -> list[BerthPlanCall]:
    sess = session or requests.Session()
    r = sess.get(f"{API_BASE}/berthplan", headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    rows = r.json().get("data") or []
    return [
        BerthPlanCall(
            terminal=row.get("terminal"),
            terminal_nm=row.get("terminalNm"),
            port_cd=row.get("portCd"),
            port_nm=row.get("portNm"),
            vessel_call=row.get("vesselCall"),
            vessel_nm=row.get("vesselNm"),
            berth_no=row.get("berthNo"),
            eta=_parse_dtm(row.get("berthnDtm")),
            cutoff=_parse_dtm(row.get("closingDtm")),
            etd=_parse_dtm(row.get("depDtm")),
            operator=row.get("operator"),
            imo_no=row.get("imoNo"),
        )
        for row in rows
    ]


def fetch_fcl_schedule(
    dep_port: str,
    arr_port: str,
    session: Optional[requests.Session] = None,
    timeout: int = 20,
) -> list[FclScheduleCall]:
    sess = session or requests.Session()
    r = sess.get(
        f"{API_BASE}/fclschedule",
        params={"depPort": dep_port, "arrPort": arr_port},
        headers=HEADERS,
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    if not body.get("result"):
        return []
    rows = body.get("data") or []
    return [
        FclScheduleCall(
            carrier_cd=row.get("shprCd"),
            carrier_nm=row.get("shprNm"),
            dep_port_cd=row.get("depPortCd"),
            dep_port_nm=row.get("depPortNm"),
            arr_port_cd=row.get("arrPortCd"),
            arr_port_nm=row.get("arrPortNm"),
            vessel_nm=row.get("vslNm"),
            voyage=row.get("voyage"),
            dep_etd=_parse_dtm(row.get("depEtd")),
            arr_eta=_parse_dtm(row.get("arrEta")),
            cargo_close=_parse_dtm(row.get("cargoCloseDtm")),
            line_plan_url=row.get("linePlanUrl"),
        )
        for row in rows
    ]


def fetch_carrier_schedules_for_port(
    arr_port: str,
    origin_ports: Optional[dict[str, str]] = None,
    delay_sec: float = 0.3,
) -> list[FclScheduleCall]:
    """origin_ports(기본값: INTRA_ASIA_ORIGIN_PORTS)에 속한 모든 항구를 출발항으로 놓고
    arr_port로 오는 선사 공지 스케줄을 모아서 반환한다 (schId 기준 중복 제거)."""
    origins = origin_ports or INTRA_ASIA_ORIGIN_PORTS
    sess = requests.Session()
    seen: set[tuple] = set()
    results: list[FclScheduleCall] = []
    for dep_port in origins:
        if dep_port == arr_port:
            continue
        try:
            calls = fetch_fcl_schedule(dep_port, arr_port, session=sess)
        except requests.RequestException:
            continue
        for c in calls:
            key = (c.vessel_nm, c.voyage, c.carrier_cd)
            if key in seen:
                continue
            seen.add(key)
            results.append(c)
        time.sleep(delay_sec)
    return results


if __name__ == "__main__":
    calls = fetch_carrier_schedules_for_port("KRINC")
    print(f"인천행 선사 공지 스케줄 {len(calls)}건")
    for c in calls[:15]:
        print(c.carrier_nm, c.vessel_nm, c.voyage, c.dep_port_nm, "->", c.arr_port_nm, c.arr_eta)
