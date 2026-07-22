"""메리츠증권 어댑터 골격.

주의: 메리츠증권은 리테일 대상 공개 자동매매 REST API가 제한적이거나
공식적으로 제공되지 않을 수 있다. 실제 연동 전에 메리츠증권에
"개인용 자동매매 Open API 제공 여부"를 반드시 확인해야 한다.

API가 제공되지 않는다면:
  - Open API를 제공하는 증권사(NH/KIS/키움 등)로 계좌를 옮기거나,
  - PaperBroker로 전략만 운용/검증하는 선택지가 있다.
"""
from __future__ import annotations

from autotrader.brokers.base import BrokerAdapter
from autotrader.models import Account, Order, Position, Quote


class MeritzBroker(BrokerAdapter):
    """메리츠증권 연동(가용성 확인 필요)."""

    name = "meritz"

    def __init__(self, **credentials: str):
        self._credentials = credentials

    def connect(self) -> None:
        raise NotImplementedError(
            "메리츠증권의 개인용 자동매매 Open API 제공 여부를 먼저 확인하세요. "
            "미제공 시 NH/KIS 등 Open API 지원 증권사 사용을 권장합니다."
        )

    def get_quote(self, symbol: str) -> Quote:
        raise NotImplementedError("메리츠 API 가용성 확인 필요")

    def get_account(self) -> Account:
        raise NotImplementedError("메리츠 API 가용성 확인 필요")

    def get_position(self, symbol: str) -> Position | None:
        raise NotImplementedError("메리츠 API 가용성 확인 필요")

    def place_order(self, order: Order) -> Order:
        raise NotImplementedError("메리츠 API 가용성 확인 필요")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("메리츠 API 가용성 확인 필요")
