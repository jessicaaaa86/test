# -*- coding: utf-8 -*-
"""선사별 스케줄 스크래퍼가 따라야 하는 공통 인터페이스.

새 선사를 추가하려면:
1. 이 파일의 CarrierAdapter를 상속하는 클래스를 scrapers/carriers/<선사>.py 에 작성한다.
2. fetch()에서 해당 선사 사이트의 인천(port='INCHEON') 스케줄을 조회해
   CarrierCall 리스트로 반환한다.
3. app.py의 CARRIER_ADAPTERS 리스트에 등록한다.

선사 사이트는 로그인/세션/캡차 등 저마다 방식이 달라, 어떤 곳은 requests만으로 되고
어떤 곳은 Playwright 같은 헤드리스 브라우저가 필요할 수 있다. 이 인터페이스는 그 차이를
숨기고 app.py 쪽에서는 동일하게 다룰 수 있게 하기 위한 것이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class CarrierCall:
    carrier: str
    vessel_name: str
    voyage: Optional[str]
    port: str
    eta: Optional[str]  # ISO 8601 문자열
    etd: Optional[str]


class CarrierAdapter(Protocol):
    name: str

    def fetch(self, port: str = "INCHEON") -> list[CarrierCall]:
        """해당 선사의 공지 스케줄을 조회해 반환한다."""
        ...
