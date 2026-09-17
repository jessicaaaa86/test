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

app = Flask(__name__)

# 선사별 스크래퍼를 구현하면 여기에 등록한다. 아직은 없음 (README 참고).
CARRIER_ADAPTERS: list = []


def refresh_terminal_data(days_ahead: int = 14) -> int:
    today = date.today()
    calls = fetch_terminal_calls(today, today + timedelta(days=days_ahead))
    scraped_at = datetime.now().isoformat(timespec="seconds")
    return db.upsert_terminal_calls([c.to_dict() for c in calls], scraped_at)


def refresh_carrier_data() -> int:
    scraped_at = datetime.now().isoformat(timespec="seconds")
    count = 0
    for adapter in CARRIER_ADAPTERS:
        for call in adapter.fetch(port="INCHEON"):
            db.upsert_carrier_schedule(
                carrier=call.carrier,
                vessel_name=call.vessel_name,
                voyage=call.voyage,
                port=call.port,
                eta=call.eta,
                etd=call.etd,
                source=f"SCRAPED:{adapter.name}",
                scraped_at=scraped_at,
            )
            count += 1
    return count


@app.route("/")
def dashboard():
    rows = match.build_comparison()
    return render_template(
        "index.html",
        rows=rows,
        carrier_adapter_count=len(CARRIER_ADAPTERS),
    )


@app.route("/refresh", methods=["POST"])
def refresh():
    refresh_terminal_data()
    refresh_carrier_data()
    return redirect(url_for("dashboard"))


@app.route("/manual-eta", methods=["POST"])
def manual_eta():
    """선사 스크래퍼가 아직 없는 선사에 대해, 담당자가 선사 사이트에서 확인한
    ETA를 직접 입력해두는 임시 경로. 자동 스크래핑이 준비되기 전까지의 보완용이다."""
    carrier = request.form["carrier"].strip()
    vessel_name = request.form["vessel_name"].strip()
    eta_raw = request.form.get("eta", "").strip()
    eta_iso = None
    if eta_raw:
        eta_iso = datetime.strptime(eta_raw, "%Y-%m-%dT%H:%M").isoformat()
    db.upsert_carrier_schedule(
        carrier=carrier,
        vessel_name=vessel_name,
        voyage=request.form.get("voyage") or None,
        port="INCHEON",
        eta=eta_iso,
        etd=None,
        source="MANUAL",
        scraped_at=datetime.now().isoformat(timespec="seconds"),
    )
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5000)
