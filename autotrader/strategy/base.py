"""전략 공통 타입."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from autotrader.models import Position, Quote


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    """전략이 내놓는 매매 신호."""
    symbol: str
    type: SignalType
    quantity: int = 0
    reason: str = ""


class Strategy:
    """전략 인터페이스.

    엔진은 종목별로 최신 시세와 보유내역을 넘겨 신호를 요청한다.
    """

    def on_quote(self, quote: Quote, position: Position | None) -> Signal:
        raise NotImplementedError
