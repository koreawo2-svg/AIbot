"""NH투자증권(나무) 어댑터 골격.

NH투자증권은 공식 Open API와 모의투자를 제공한다. 실제 연동 시
아래 메서드 내부를 NH Open API 호출로 채우면 된다.

필요한 것(발급 후 config/환경변수로 주입):
  - APP KEY / APP SECRET (NH Open API 신청)
  - 계좌번호
  - 접근토큰(access token) 발급 엔드포인트

주의: 반드시 모의투자 계좌로 충분히 검증한 뒤 실계좌에 연결할 것.
"""
from __future__ import annotations

from autotrader.brokers.base import BrokerAdapter
from autotrader.models import Account, Order, Position, Quote


class NHBroker(BrokerAdapter):
    """NH투자증권 Open API 연동(구현 예정)."""

    name = "nh"

    def __init__(self, app_key: str, app_secret: str, account_no: str, *, paper: bool = True):
        self._app_key = app_key
        self._app_secret = app_secret
        self._account_no = account_no
        self._paper = paper
        self._token: str | None = None

    def connect(self) -> None:
        # TODO: NH Open API 토큰 발급 엔드포인트 호출 후 self._token 저장
        raise NotImplementedError(
            "NH(나무) 어댑터는 API 키 발급 후 구현 예정입니다. "
            "우선 PaperBroker로 전략을 검증하세요."
        )

    def get_quote(self, symbol: str) -> Quote:
        raise NotImplementedError("NH 시세 조회 API 연동 필요")

    def get_account(self) -> Account:
        raise NotImplementedError("NH 계좌 조회 API 연동 필요")

    def get_position(self, symbol: str) -> Position | None:
        raise NotImplementedError("NH 잔고 조회 API 연동 필요")

    def place_order(self, order: Order) -> Order:
        raise NotImplementedError("NH 주문 API 연동 필요")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("NH 주문취소 API 연동 필요")
