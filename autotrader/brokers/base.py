"""증권사 어댑터 공통 인터페이스.

모든 증권사(NH 나무 / 메리츠 / 신한 / 모의)는 이 인터페이스를 구현한다.
전략·엔진 코드는 이 추상 클래스에만 의존하므로 증권사를 자유롭게 갈아끼울 수 있다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from autotrader.models import Account, Order, Position, Quote


class BrokerAdapter(ABC):
    """증권사 연동 공통 규약."""

    #: 사람이 읽을 수 있는 증권사 이름
    name: str = "base"

    @abstractmethod
    def connect(self) -> None:
        """로그인/토큰 발급 등 연결 준비."""

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """단일 종목 현재가 조회."""

    @abstractmethod
    def get_account(self) -> Account:
        """현금·보유종목 등 계좌 상태 조회."""

    @abstractmethod
    def get_position(self, symbol: str) -> Position | None:
        """특정 종목 보유 내역 조회(없으면 None)."""

    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """주문 접수. 체결 결과가 반영된 Order를 돌려준다."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """미체결 주문 취소."""

    def disconnect(self) -> None:
        """연결 종료(선택 구현)."""
        return None
