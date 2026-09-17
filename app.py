# -*- coding: utf-8 -*-
"""선사 스케줄 vs 터미널 접안 스케줄 비교 대시보드.

실행:
    pip install -r requirements.txt
    python app.py
그 다음 브라우저에서 http://localhost:5000 접속.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import Flask, redirect, render_template, request, url_for

import db
import match
from scrapers.icon_terminal import fetch_terminal_calls
from scrapers.tradlinx import fetch_berthplan, fetch_carrier_schedules_for_port

app = Flask(__name__)

# 터미널 접안 스케줄을 iCON(정부기관, 공식)에서 직접 받아오는 항구. 그 외 항구는
# Tradlinx의 전국 터미널 접안계획(berthplan)으로 보완한다.
ICON_PORT_CD = "KRINC"

# 대시보드에서 다루는 도착항 목록 (선사 공지 스케줄 조회 대상).
# 부산 북항/신항을 포함해 필요한 항구를 여기에 추가하면 된다.
TRACKED_PORTS = {
    "KRINC": "인천",
    "KRPUS": "부산(북항)",
    "KRBNP": "부산(신항)",
}


def refresh_icon_terminal_data(days_ahead: int = 14) -> int:
    """인천은 인천항만공사 iCON에서 직접 가져온다 (공식 정부기관 데이터)."""
    today = date.today()
    calls = fetch_terminal_calls(today, today + timedelta(days=days_ahead))
    scraped_at = datetime.now().isoformat(timespec="seconds")
    return db.upsert_terminal_calls([c.to_dict() for c in calls], scraped_at, source="ICON")


def refresh_tradlinx_terminal_data() -> int:
    """인천을 제외한 나머지 항구(부산 등)는 Tradlinx의 전국 터미널 접안계획으로 채운다."""
    scraped_at = datetime.now().isoformat(timespec="seconds")
    calls = fetch_berthplan()
    rows = [
        {
            "port_cd": c.port_cd,
            "port_nm": c.port_nm,
            "terminal": c.terminal_nm or c.terminal,
            "voyage_code": c.vessel_call,
            "vessel_name": c.vessel_nm,
            "berth": c.berth_no,
            "eta": c.eta,
            "eta_confirmed": c.eta is not None,
            "cutoff": c.cutoff,
            "etd": c.etd,
            "etd_confirmed": c.etd is not None,
            "carrier": c.operator,
        }
        for c in calls
        if c.port_cd != ICON_PORT_CD and c.vessel_nm
    ]
    return db.upsert_terminal_calls(rows, scraped_at, source="TRADLINX")


def refresh_carrier_data() -> int:
    """추적 중인 각 항구에 대해 Tradlinx 선사 공지 스케줄(FCL)을 받아온다."""
    scraped_at = datetime.now().isoformat(timespec="seconds")
    total = 0
    for port_cd in TRACKED_PORTS:
        calls = fetch_carrier_schedules_for_port(port_cd)
        rows = [
            {
                "carrier": c.carrier_nm,
                "vessel_name": c.vessel_nm,
                "voyage": c.voyage,
                "port": port_cd,
                "eta": c.arr_eta,
                "etd": c.dep_etd,
            }
            for c in calls
            if c.vessel_nm
        ]
        total += db.upsert_carrier_schedules(rows, source="TRADLINX", scraped_at=scraped_at)
    return total


@app.route("/")
def dashboard():
    port_cd = request.args.get("port") or None
    rows = match.build_comparison(port_cd=port_cd)
    return render_template(
        "index.html",
        rows=rows,
        tracked_ports=TRACKED_PORTS,
        selected_port=port_cd,
    )


@app.route("/refresh", methods=["POST"])
def refresh():
    refresh_icon_terminal_data()
    refresh_tradlinx_terminal_data()
    refresh_carrier_data()
    return redirect(url_for("dashboard"))


@app.route("/manual-eta", methods=["POST"])
def manual_eta():
    """자동 수집으로 못 찾은 선사 ETA를 담당자가 직접 입력해두는 보완 경로."""
    carrier = request.form["carrier"].strip()
    vessel_name = request.form["vessel_name"].strip()
    port_cd = request.form.get("port_cd") or "KRINC"
    eta_raw = request.form.get("eta", "").strip()
    eta_iso = None
    if eta_raw:
        eta_iso = datetime.strptime(eta_raw, "%Y-%m-%dT%H:%M").isoformat()
    db.upsert_carrier_schedule(
        carrier=carrier,
        vessel_name=vessel_name,
        voyage=request.form.get("voyage") or None,
        port=port_cd,
        eta=eta_iso,
        etd=None,
        source="MANUAL",
        scraped_at=datetime.now().isoformat(timespec="seconds"),
    )
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5000)
