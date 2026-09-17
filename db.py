# -*- coding: utf-8 -*-
"""SQLite 저장소.

두 종류의 데이터를 저장한다.
- terminal_calls: iCON(터미널) 쪽에서 스크래핑한 접안/출항 스케줄 (기준 데이터)
- carrier_schedules: 선사가 공지하는 스케줄. 자동 스크래핑 결과(source='SCRAPED:<선사>')
  또는 수동 입력(source='MANUAL')이 들어갈 수 있다. 선사별 스크래퍼가 아직 없는 동안에는
  담당자가 선사 사이트에서 확인한 값을 수동으로 입력해 비교 화면을 바로 쓸 수 있게 한다.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "schedule.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS terminal_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    port_cd TEXT NOT NULL DEFAULT 'KRINC',
    port_nm TEXT NOT NULL DEFAULT '인천',
    terminal TEXT NOT NULL,
    berth TEXT,
    voyage_code TEXT,
    voyage_in TEXT,
    voyage_out TEXT,
    year TEXT,
    vessel_name TEXT NOT NULL,
    vessel_name_norm TEXT NOT NULL,
    eta TEXT,
    eta_confirmed INTEGER,
    cutoff TEXT,
    etd TEXT,
    etd_confirmed INTEGER,
    carrier TEXT,
    discharge_qty INTEGER,
    load_qty INTEGER,
    shift INTEGER,
    source TEXT NOT NULL DEFAULT 'ICON',
    scraped_at TEXT NOT NULL,
    UNIQUE(port_cd, terminal, voyage_code, vessel_name)
);

CREATE TABLE IF NOT EXISTS carrier_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carrier TEXT NOT NULL,
    vessel_name TEXT NOT NULL,
    vessel_name_norm TEXT NOT NULL,
    voyage TEXT,
    port TEXT,
    eta TEXT,
    etd TEXT,
    source TEXT NOT NULL,
    scraped_at TEXT NOT NULL,
    UNIQUE(carrier, vessel_name, voyage, port)
);

CREATE INDEX IF NOT EXISTS idx_terminal_calls_vessel ON terminal_calls(vessel_name_norm);
CREATE INDEX IF NOT EXISTS idx_carrier_schedules_vessel ON carrier_schedules(vessel_name_norm);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def normalize_carrier_name(name: str | None) -> str:
    """선사명을 매칭용으로 정규화한다 (대소문자/공백/'CO., LTD.' 등 법인 표기 제거)."""
    if not name:
        return ""
    return "".join(ch for ch in name.upper() if ch.isalnum())


def normalize_vessel_name(name: str) -> str:
    """선박명을 매칭용으로 정규화한다.

    선사 사이트와 iCON은 표기가 조금씩 다를 수 있다 (대소문자, 공백,
    'M/V' 접두어, 하이픈 등). 매칭 정확도를 위해 이런 차이를 없앤다.
    """
    if not name:
        return ""
    n = name.upper().strip()
    for prefix in ("M/V ", "MV ", "S/S "):
        if n.startswith(prefix):
            n = n[len(prefix):]
    n = "".join(ch for ch in n if ch.isalnum())
    return n


def upsert_terminal_calls(calls: list[dict], scraped_at: str, source: str = "ICON") -> int:
    """터미널 접안 스케줄 레코드를 저장한다 (iCON 또는 Tradlinx berthplan 등).

    같은 항구/터미널/항차/선박명이면 최신 값으로 덮어쓴다. 각 레코드 dict에
    port_cd/port_nm이 없으면 기본값(인천, KRINC)을 쓴다 - iCON은 인천 전용이라
    호출부에서 매번 넣지 않아도 되게 하기 위함이다.
    """
    with get_conn() as conn:
        for c in calls:
            row = {
                "port_cd": "KRINC",
                "port_nm": "인천",
                "berth": None,
                "voyage_in": None,
                "voyage_out": None,
                "year": None,
                "cutoff": None,
                "etd": None,
                "etd_confirmed": None,
                "carrier": None,
                "discharge_qty": None,
                "load_qty": None,
                "shift": None,
                **c,
                "vessel_name_norm": normalize_vessel_name(c["vessel_name"]),
                "source": source,
                "scraped_at": scraped_at,
            }
            conn.execute(
                """
                INSERT INTO terminal_calls (
                    port_cd, port_nm, terminal, berth, voyage_code, voyage_in, voyage_out, year,
                    vessel_name, vessel_name_norm, eta, eta_confirmed, cutoff,
                    etd, etd_confirmed, carrier, discharge_qty, load_qty, shift, source, scraped_at
                ) VALUES (
                    :port_cd, :port_nm, :terminal, :berth, :voyage_code, :voyage_in, :voyage_out, :year,
                    :vessel_name, :vessel_name_norm, :eta, :eta_confirmed, :cutoff,
                    :etd, :etd_confirmed, :carrier, :discharge_qty, :load_qty, :shift, :source, :scraped_at
                )
                ON CONFLICT(port_cd, terminal, voyage_code, vessel_name) DO UPDATE SET
                    port_nm=excluded.port_nm,
                    berth=excluded.berth,
                    voyage_in=excluded.voyage_in,
                    voyage_out=excluded.voyage_out,
                    year=excluded.year,
                    eta=excluded.eta,
                    eta_confirmed=excluded.eta_confirmed,
                    cutoff=excluded.cutoff,
                    etd=excluded.etd,
                    etd_confirmed=excluded.etd_confirmed,
                    carrier=excluded.carrier,
                    discharge_qty=excluded.discharge_qty,
                    load_qty=excluded.load_qty,
                    shift=excluded.shift,
                    source=excluded.source,
                    scraped_at=excluded.scraped_at
                """,
                row,
            )
        return len(calls)


def upsert_carrier_schedule(
    carrier: str,
    vessel_name: str,
    voyage: str | None,
    port: str,
    eta: str | None,
    etd: str | None,
    source: str,
    scraped_at: str,
) -> None:
    """선사 공지 스케줄 한 건을 저장한다 (수동 입력 등 단건 용도)."""
    upsert_carrier_schedules(
        [
            {
                "carrier": carrier,
                "vessel_name": vessel_name,
                "voyage": voyage,
                "port": port,
                "eta": eta,
                "etd": etd,
            }
        ],
        source=source,
        scraped_at=scraped_at,
    )


def upsert_carrier_schedules(calls: list[dict], source: str, scraped_at: str) -> int:
    """선사 공지 스케줄 여러 건을 저장한다 (예: Tradlinx 대량 조회 결과).

    같은 선사/선박명/항차/항구 조합이면 최신 값으로 덮어쓴다.
    """
    with get_conn() as conn:
        for c in calls:
            conn.execute(
                """
                INSERT INTO carrier_schedules (
                    carrier, vessel_name, vessel_name_norm, voyage, port, eta, etd, source, scraped_at
                ) VALUES (:carrier, :vessel_name, :vessel_name_norm, :voyage, :port, :eta, :etd, :source, :scraped_at)
                ON CONFLICT(carrier, vessel_name, voyage, port) DO UPDATE SET
                    eta=excluded.eta,
                    etd=excluded.etd,
                    source=excluded.source,
                    scraped_at=excluded.scraped_at
                """,
                {
                    **c,
                    "vessel_name_norm": normalize_vessel_name(c["vessel_name"]),
                    "source": source,
                    "scraped_at": scraped_at,
                },
            )
        return len(calls)
