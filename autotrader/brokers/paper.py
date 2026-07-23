"""모의투자(페이퍼 트레이딩) 브로커.

실제 증권사 API 없이 전략을 검증하기 위한 시뮬레이터.
- 시장가 주문: 현재가로 즉시 체결
- 지정가 매수: 현재가 <= 지정가일 때 체결
- 지정가 매도: 현재가 >= 지정가일 때 체결
- 잔고/수수료를 반영해 현금과 보유종목을 갱신
"""
from __future__ import annotations

import itertools

from autotrader.brokers.base import BrokerAdapter
from autotrader.market_data import MarketDataFeed
from autotrader.models import (
    Account,
    Order,
    OrderStatus,
    OrderType,
    Position,
    Quote,
    Side,
)


class PaperBroker(BrokerAdapter):
    """메모리상에서 동작하는 모의 브로커."""

    name = "paper"

    def __init__(
        self,
        feed: MarketDataFeed,
        cash: float = 10_000_000.0,
        fee_rate: float = 0.00015,   # 매매 수수료(예시)
        tax_rate: float = 0.0018,    # 매도 시 증권거래세(예시)
    ):
        self._feed = feed
        self._account = Account(cash=cash)
        self._fee_rate = fee_rate
        self._tax_rate = tax_rate
        self._order_seq = itertools.count(1)
        self._last_quotes: dict[str, Quote] = {}

    # --- 조회 ---
    def connect(self) -> None:
        return None

    def get_quote(self, symbol: str) -> Quote:
        quote = self._feed.next_quote(symbol)
        self._last_quotes[symbol] = quote
        return quote

    def get_account(self) -> Account:
        return self._account

    def get_position(self, symbol: str) -> Position | None:
        return self._account.positions.get(symbol)

    def equity(self) -> float:
        """현금 + 보유종목 평가금액(가장 최근 시세 기준)."""
        return self._account.equity(self._last_quotes)

    def last_prices(self) -> dict[str, float]:
        """종목별 가장 최근 체결 시세."""
        return {s: q.price for s, q in self._last_quotes.items()}

    # --- 주문 ---
    def place_order(self, order: Order) -> Order:
        quote = self._last_quotes.get(order.symbol)
        if quote is None:
            quote = self.get_quote(order.symbol)

        order.order_id = f"PAPER-{next(self._order_seq)}"
        fill_price = self._fill_price(order, quote.price)
        if fill_price is None:
            order.status = OrderStatus.PENDING  # 지정가 미체결
            return order

        if order.side == Side.BUY:
            return self._execute_buy(order, fill_price)
        return self._execute_sell(order, fill_price)

    def cancel_order(self, order_id: str) -> bool:
        # 즉시 체결 모델이라 취소할 미체결 주문이 유지되지 않는다.
        return True

    # --- 내부 헬퍼 ---
    def _fill_price(self, order: Order, market_price: float) -> float | None:
        """체결 여부/가격 판정. 미체결이면 None."""
        if order.order_type == OrderType.MARKET:
            return market_price
        # 지정가
        if order.side == Side.BUY and market_price <= order.limit_price:
            return market_price
        if order.side == Side.SELL and market_price >= order.limit_price:
            return market_price
        return None

    def _execute_buy(self, order: Order, price: float) -> Order:
        gross = price * order.quantity
        cost = gross * (1 + self._fee_rate)
        if cost > self._account.cash:
            order.status = OrderStatus.REJECTED
            return order

        self._account.cash -= cost
        pos = self._account.positions.get(order.symbol)
        if pos is None:
            self._account.positions[order.symbol] = Position(
                symbol=order.symbol, quantity=order.quantity, avg_price=price
            )
        else:
            total_qty = pos.quantity + order.quantity
            pos.avg_price = (pos.avg_price * pos.quantity + price * order.quantity) / total_qty
            pos.quantity = total_qty

        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.filled_price = price
        return order

    def _execute_sell(self, order: Order, price: float) -> Order:
        pos = self._account.positions.get(order.symbol)
        if pos is None or pos.quantity < order.quantity:
            order.status = OrderStatus.REJECTED
            return order

        gross = price * order.quantity
        proceeds = gross * (1 - self._fee_rate - self._tax_rate)
        self._account.cash += proceeds
        pos.quantity -= order.quantity
        if pos.quantity == 0:
            del self._account.positions[order.symbol]

        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.filled_price = price
        return order
