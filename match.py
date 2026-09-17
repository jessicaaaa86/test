# -*- coding: utf-8 -*-
"""터미널 접안 스케줄(iCON)과 선사 공지 스케줄을 선박명 기준으로 매칭해 비교한다."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from db import get_conn

# 이 시간(시간 단위) 이상 차이나면 화면에서 강조 표시한다.
DIFF_ALERT_HOURS = 6.0


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def build_comparison(days_ahead: int = 14) -> list[dict]:
    """터미널 접안 예정 목록에 매칭되는 선사 공지 스케줄(있으면)을 붙여서 반환한다.

    선사 공지 스케줄이 여러 건 있으면 iCON 접안일시와 가장 가까운 시점에
    스크래핑/입력된 것을 우선한다 (가장 최근에 확인된 값이 신뢰도가 높다고 가정).
    """
    with get_conn() as conn:
        terminal_rows = conn.execute(
            """
            SELECT * FROM terminal_calls
            WHERE eta IS NULL OR eta >= datetime('now', '-2 days')
            ORDER BY eta IS NULL, eta ASC
            """
        ).fetchall()

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
        carrier_match = candidates[0] if candidates else None

        terminal_eta = _parse_iso(t["eta"])
        carrier_eta = _parse_iso(carrier_match["eta"]) if carrier_match else None

        diff_hours = None
        if terminal_eta and carrier_eta:
            diff_hours = round((terminal_eta - carrier_eta).total_seconds() / 3600, 1)

        results.append(
            {
                "vessel_name": t["vessel_name"],
                "terminal": t["terminal"],
                "berth": t["berth"],
                "voyage_code": t["voyage_code"],
                "carrier": t["carrier"],
                "terminal_eta": t["eta"],
                "terminal_eta_confirmed": bool(t["eta_confirmed"]),
                "terminal_etd": t["etd"],
                "carrier_announced_eta": carrier_match["eta"] if carrier_match else None,
                "carrier_announced_source": carrier_match["source"] if carrier_match else None,
                "diff_hours": diff_hours,
                "diff_alert": diff_hours is not None and abs(diff_hours) >= DIFF_ALERT_HOURS,
                "has_carrier_data": carrier_match is not None,
            }
        )
    return results
