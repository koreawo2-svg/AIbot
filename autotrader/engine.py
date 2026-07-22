"""트레이딩 엔진.

브로커 어댑터와 전략을 연결해 다음 루프를 반복한다:
  시세 조회 -> 보유내역 확인 -> 전략 신호 -> 주문 실행 -> 로그
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from autotrader.brokers.base import BrokerAdapter
from autotrader.models import Order, OrderType, Side
from autotrader.strategy.base import SignalType, Strategy

logger = logging.getLogger("autotrader.engine")


@dataclass
class TradeRecord:
    """체결/신호 기록."""
    symbol: str
    action: str
    quantity: int
    price: float
    reason: str


class TradingEngine:
    """단일 브로커 + 단일 전략으로 여러 종목을 운용한다."""

    def __init__(
        self,
        broker: BrokerAdapter,
        strategy: Strategy,
        symbols: list[str],
        order_type: OrderType = OrderType.MARKET,
    ):
        self._broker = broker
        self._strategy = strategy
        self._symbols = symbols
        self._order_type = order_type
        self.history: list[TradeRecord] = []

    def start(self) -> None:
        self._broker.connect()
        logger.info("브로커 연결: %s", self._broker.name)

    def step(self) -> list[TradeRecord]:
        """모든 종목을 1회 평가하고 발생한 체결 기록을 반환."""
        step_records: list[TradeRecord] = []
        for symbol in self._symbols:
            quote = self._broker.get_quote(symbol)
            position = self._broker.get_position(symbol)
            signal = self._strategy.on_quote(quote, position)

            if signal.type == SignalType.HOLD or signal.quantity <= 0:
                continue

            side = Side.BUY if signal.type == SignalType.BUY else Side.SELL
            order = Order(
                symbol=symbol,
                side=side,
                quantity=signal.quantity,
                order_type=self._order_type,
                limit_price=quote.price if self._order_type == OrderType.LIMIT else None,
            )
            result = self._broker.place_order(order)

            rec = TradeRecord(
                symbol=symbol,
                action=f"{side.value}/{result.status.value}",
                quantity=result.filled_quantity,
                price=result.filled_price,
                reason=signal.reason,
            )
            self.history.append(rec)
            step_records.append(rec)
            logger.info(
                "%s %s x%d @%.2f | %s",
                symbol, rec.action, rec.quantity, rec.price, signal.reason,
            )
        return step_records

    def run(self, steps: int) -> None:
        """지정한 횟수만큼 step을 반복(모의/백테스트용)."""
        self.start()
        for _ in range(steps):
            self.step()
