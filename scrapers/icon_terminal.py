# -*- coding: utf-8 -*-
"""
인천항만공사(IPA) iCON 통합정보 - 선석배정현황(텍스트) 스크래퍼.

공개된 대민 서비스(로그인 불필요)를 그대로 조회한다.
https://scon.icpa.or.kr/main.do?menuKey=19

이 데이터가 "터미널 접안 스케줄"의 기준(ground truth) 역할을 한다:
인천 5개 컨테이너/여객 터미널(선광 SNCT, 한진 HJIT, E1CT, 인천 ICT, 국제여객부두)의
접안(예정)일시 / 출항(예정)일시를 선사명과 함께 한번에 제공한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://scon.icpa.or.kr"
LIST_URL = f"{BASE_URL}/vescall/list.do"

# 터미널명 -> iCON 내부 코드 (searchTermCd). 빈 문자열이면 전체.
TERMINAL_CODES = {
    "전체": "",
    "선광": "IT001",  # 선광신컨테이너터미널 (SNCT)
    "한진": "IT004",  # 한진인천컨테이너터미널 (HJIT)
    "E1": "IT002",    # E1컨테이너터미널 (E1CT)
    "인천": "IT003",  # 인천컨테이너터미널 (ICT)
    "국제": "IT006",  # 국제여객부두 (IFPC)
}

_DT_RE = re.compile(r"\(?(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\)?")


def _parse_dt(cell_text: str) -> tuple[Optional[datetime], bool]:
    """'2026-09-17 03:00' 또는 '(2026-09-17 03:00)' 형태의 셀 텍스트를 파싱한다.

    괄호가 있으면 iCON이 아직 확정하지 않은 예정 시각이라는 뜻이므로
    confirmed=False 로 표시한다. 빈 문자열이면 (None, False)를 반환한다.
    """
    cell_text = (cell_text or "").strip()
    if not cell_text:
        return None, False
    m = _DT_RE.search(cell_text)
    if not m:
        return None, False
    confirmed = not cell_text.startswith("(")
    dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
    return dt, confirmed


@dataclass
class TerminalCall:
    terminal: str            # 선광 / 한진 / E1 / 인천 / 국제
    berth: str                # 선석 (예: B1)
    voyage_code: str          # 모선항차 코드 (예: CKSC-011)
    voyage_in: str            # 입항차 (예: 2609N)
    voyage_out: str           # 출항차 (예: 2610S)
    year: str
    vessel_name: str
    eta: Optional[datetime]
    eta_confirmed: bool
    cutoff: Optional[datetime]
    etd: Optional[datetime]
    etd_confirmed: bool
    carrier: str
    discharge_qty: Optional[int]
    load_qty: Optional[int]
    shift: Optional[int]

    @property
    def status(self) -> str:
        """접안/출항 확정 여부로부터 대략적인 진행 상태를 유도한다."""
        if self.eta_confirmed and self.etd_confirmed:
            return "출항완료"
        if self.eta_confirmed and not self.etd_confirmed:
            return "접안중"
        return "입항예정"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["eta"] = self.eta.isoformat() if self.eta else None
        d["cutoff"] = self.cutoff.isoformat() if self.cutoff else None
        d["etd"] = self.etd.isoformat() if self.etd else None
        d["status"] = self.status
        return d


def _int_or_none(text: str) -> Optional[int]:
    text = (text or "").replace(",", "").strip()
    if not text or not text.lstrip("-").isdigit():
        return None
    return int(text)


def fetch_terminal_calls(
    start: date,
    end: date,
    terminal: str = "전체",
    session: Optional[requests.Session] = None,
    timeout: int = 20,
) -> list[TerminalCall]:
    """지정 기간의 인천항 선석배정현황(텍스트)을 모두 가져온다.

    recordCountPerPage 를 크게 잡아 페이지네이션 없이 한번에 받는다.
    """
    sess = session or requests.Session()
    payload = {
        "currentPageNo": "1",
        "menuKey": "19",
        "recordCountPerPage": "2000",
        "searchTermCd": TERMINAL_CODES.get(terminal, ""),
        "searchStartDt": start.strftime("%Y-%m-%d"),
        "searchEndDt": end.strftime("%Y-%m-%d"),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": f"{BASE_URL}/main.do?menuKey=19",
    }
    resp = sess.post(LIST_URL, data=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return _parse_table(resp.text)


def _parse_table(html: str) -> list[TerminalCall]:
    soup = BeautifulSoup(html, "html.parser")
    board = soup.select_one("div.table-board table")
    if board is None:
        return []
    rows = board.select("tbody > tr")
    calls: list[TerminalCall] = []
    for tr in rows:
        cells = tr.find_all("td")
        if len(cells) < 13:
            continue

        voyage_cell = cells[3]
        voyage_code = voyage_cell.contents[0].get_text(strip=True) if voyage_cell.contents else ""
        sub = voyage_cell.select_one(".sub_txt")
        voyage_in, voyage_out = "", ""
        if sub:
            parts = sub.get_text(strip=True).split("/")
            if len(parts) == 2:
                voyage_in, voyage_out = parts[0], parts[1]

        vessel_cell = cells[5]
        vessel_name = vessel_cell.contents[0].get_text(strip=True) if vessel_cell.contents else vessel_cell.get_text(strip=True)

        eta, eta_confirmed = _parse_dt(cells[6].get_text())
        cutoff, _ = _parse_dt(cells[7].get_text())
        etd, etd_confirmed = _parse_dt(cells[8].get_text())

        calls.append(
            TerminalCall(
                terminal=cells[1].get_text(strip=True),
                berth=cells[2].get_text(strip=True),
                voyage_code=voyage_code,
                voyage_in=voyage_in,
                voyage_out=voyage_out,
                year=cells[4].get_text(strip=True),
                vessel_name=vessel_name,
                eta=eta,
                eta_confirmed=eta_confirmed,
                cutoff=cutoff,
                etd=etd,
                etd_confirmed=etd_confirmed,
                carrier=cells[9].get_text(strip=True),
                discharge_qty=_int_or_none(cells[10].get_text()),
                load_qty=_int_or_none(cells[11].get_text()),
                shift=_int_or_none(cells[12].get_text()) if len(cells) > 12 else None,
            )
        )
    return calls


if __name__ == "__main__":
    from datetime import timedelta

    today = date.today()
    results = fetch_terminal_calls(today, today + timedelta(days=7))
    print(f"{len(results)}건 조회됨")
    for c in results[:10]:
        print(c.terminal, c.berth, c.vessel_name, c.carrier, c.eta, c.eta_confirmed, c.status)
