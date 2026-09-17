# -*- coding: utf-8 -*-
"""터미널 접안 스케줄과 선사 공지 스케줄을 선박명 기준으로 매칭해 비교한다."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from db import get_conn, normalize_carrier_name

# 이 시간(시간 단위) 이상 차이나면 화면에서 강조 표시한다.
DIFF_ALERT_HOURS = 6.0


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _voyage_matches(terminal_row, candidate) -> bool:
    voy = (candidate["voyage"] or "").strip().upper()
    if not voy:
        return False
    return voy in {
        (terminal_row["voyage_in"] or "").strip().upper(),
        (terminal_row["voyage_out"] or "").strip().upper(),
        (terminal_row["voyage_code"] or "").strip().upper(),
    }


def _carrier_matches(terminal_row, candidate) -> bool:
    t = normalize_carrier_name(terminal_row["carrier"])
    c = normalize_carrier_name(candidate["carrier"])
    if not t or not c:
        return False
    return t in c or c in t


# 선박은 같은 이름으로 몇 주 간격을 두고 반복 기항하므로(순환 서비스),
# ETA가 이보다 더 벌어진 후보는 다른 항차로 보고 매칭에서 제외한다.
MAX_CANDIDATE_ETA_GAP_DAYS = 4.0


def _pick_best_candidate(terminal_row, candidates: list):
    """같은 선박명으로 여러 선사가 공동 배선(joint service)을 공지하거나, 같은 선박이
    몇 주 간격으로 반복 기항하는 경우가 흔하다. 먼저 ETA가 터미널 ETA와 가까운
    (MAX_CANDIDATE_ETA_GAP_DAYS 이내) 후보로만 추리고, 그 안에서 항차 일치 >
    선사명 일치 > 가장 가까운 ETA 순으로 고른다. 가까운 후보가 아예 없으면(=선박은
    같아도 다른 항차/주기로 보임) 매칭하지 않는다."""
    if not candidates:
        return None

    terminal_eta = _parse_iso(terminal_row["eta"])
    if terminal_eta is None:
        # 터미널 쪽 ETA를 모르면 시간 비교가 불가능하니, 항차/선사명이 맞는 것만 인정한다.
        for c in candidates:
            if _voyage_matches(terminal_row, c):
                return c
        for c in candidates:
            if _carrier_matches(terminal_row, c):
                return c
        return None

    nearby = []
    for c in candidates:
        c_eta = _parse_iso(c["eta"])
        if c_eta is None:
            continue
        gap_days = abs((c_eta - terminal_eta).total_seconds()) / 86400
        if gap_days <= MAX_CANDIDATE_ETA_GAP_DAYS:
            nearby.append((gap_days, c))
    if not nearby:
        return None

    for _, c in nearby:
        if _voyage_matches(terminal_row, c):
            return c
    for _, c in nearby:
        if _carrier_matches(terminal_row, c):
            return c
    nearby.sort(key=lambda pair: pair[0])
    return nearby[0][1]


def build_comparison(days_ahead: int = 14, port_cd: Optional[str] = None) -> list[dict]:
    """터미널 접안 예정 목록에 매칭되는 선사 공지 스케줄(있으면)을 붙여서 반환한다."""
    with get_conn() as conn:
        query = """
            SELECT * FROM terminal_calls
            WHERE (eta IS NULL OR eta >= datetime('now', '-2 days'))
        """
        params: list = []
        if port_cd:
            query += " AND port_cd = ?"
            params.append(port_cd)
        query += " ORDER BY eta IS NULL, eta ASC"
        terminal_rows = conn.execute(query, params).fetchall()

        carrier_rows = conn.execute(
            "SELECT * FROM carrier_schedules ORDER BY scraped_at DESC"
        ).fetchall()

    # 선박명(정규화) -> 선사 공지 레코드 목록
    by_vessel: dict[str, list] = {}
    for row in carrier_rows:
        by_vessel.setdefault(row["vessel_name_norm"], []).append(row)

    results = []
    for t in terminal_rows:
        candidates = by_vessel.get(t["vessel_name_norm"], [])
        carrier_match = _pick_best_candidate(t, candidates)

        terminal_eta = _parse_iso(t["eta"])
        carrier_eta = _parse_iso(carrier_match["eta"]) if carrier_match else None

        diff_hours = None
        if terminal_eta and carrier_eta:
            diff_hours = round((terminal_eta - carrier_eta).total_seconds() / 3600, 1)

        results.append(
            {
                "vessel_name": t["vessel_name"],
                "port_cd": t["port_cd"],
                "port_nm": t["port_nm"],
                "terminal": t["terminal"],
                "berth": t["berth"],
                "voyage_code": t["voyage_code"],
                "carrier": t["carrier"],
                "terminal_eta": t["eta"],
                "terminal_eta_confirmed": bool(t["eta_confirmed"]),
                "terminal_etd": t["etd"],
                "terminal_source": t["source"],
                "carrier_announced_eta": carrier_match["eta"] if carrier_match else None,
                "carrier_announced_by": carrier_match["carrier"] if carrier_match else None,
                "carrier_announced_source": carrier_match["source"] if carrier_match else None,
                "diff_hours": diff_hours,
                "diff_alert": diff_hours is not None and abs(diff_hours) >= DIFF_ALERT_HOURS,
                "has_carrier_data": carrier_match is not None,
            }
        )
    return results
