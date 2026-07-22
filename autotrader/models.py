"""핵심 데이터 모델과 열거형.

증권사/전략과 무관하게 공통으로 쓰는 자료구조를 정의한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(str, Enum):
    """매매 방향."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """주문 유형."""
    MARKET = "MARKET"   # 시장가
    LIMIT = "LIMIT"     # 지정가


class OrderStatus(str, Enum):
    """주문 상태."""
    PENDING = "PENDING"       # 접수 대기/미체결
    FILLED = "FILLED"         # 전량 체결
    PARTIAL = "PARTIAL"       # 부분 체결
    CANCELED = "CANCELED"     # 취소
    REJECTED = "REJECTED"     # 거부


@dataclass
class Quote:
    """단일 종목의 현재 시세 스냅샷."""
    symbol: str
    price: float
    timestamp: datetime
    volume: int = 0


@dataclass
class Order:
    """주문 요청/결과."""
    symbol: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    filled_price: float = 0.0
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("지정가 주문에는 limit_price가 필요합니다.")


@dataclass
class Position:
    """보유 종목."""
    symbol: str
    quantity: int
    avg_price: float

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """평가 손익률(%)."""
        if self.avg_price == 0:
            return 0.0
        return (current_price - self.avg_price) / self.avg_price * 100.0


@dataclass
class Account:
    """계좌 요약."""
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)

    def equity(self, quotes: dict[str, Quote]) -> float:
        """현금 + 보유종목 평가금액."""
        total = self.cash
        for symbol, pos in self.positions.items():
            q = quotes.get(symbol)
            if q:
                total += pos.quantity * q.price
        return total
