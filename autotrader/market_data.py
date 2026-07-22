"""시세 피드.

- ReplayFeed: 정해진 가격 시퀀스를 순서대로 재생(백테스트/테스트용, 결정적).
- RandomWalkFeed: 시드 기반 랜덤워크로 가격을 생성(모의 데모용, 시드 고정 시 결정적).

실제 증권사 어댑터는 이 피드 대신 API 실시간 시세를 사용한다.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from autotrader.models import Quote


class MarketDataFeed(ABC):
    """종목별 다음 시세를 제공하는 피드."""

    @abstractmethod
    def next_quote(self, symbol: str) -> Quote:
        """해당 종목의 다음 시세를 반환."""


class ReplayFeed(MarketDataFeed):
    """미리 정해진 가격 목록을 순서대로 재생한다.

    가격이 소진되면 마지막 값을 계속 반환한다.
    """

    def __init__(self, prices: dict[str, list[float]], start: datetime | None = None):
        self._prices = {s: list(p) for s, p in prices.items()}
        self._idx: dict[str, int] = {s: 0 for s in prices}
        self._t = start or datetime(2024, 1, 1, 9, 0, 0)

    def next_quote(self, symbol: str) -> Quote:
        series = self._prices.get(symbol)
        if not series:
            raise KeyError(f"'{symbol}' 종목의 가격 데이터가 없습니다.")
        i = min(self._idx[symbol], len(series) - 1)
        self._idx[symbol] = i + 1
        self._t += timedelta(seconds=1)
        return Quote(symbol=symbol, price=float(series[i]), timestamp=self._t)


class RandomWalkFeed(MarketDataFeed):
    """시드 기반 랜덤워크로 가격을 생성하는 데모용 피드."""

    def __init__(
        self,
        start_prices: dict[str, float],
        volatility: float = 0.01,
        seed: int = 42,
        start: datetime | None = None,
    ):
        self._prices = dict(start_prices)
        self._vol = volatility
        self._rng = random.Random(seed)
        self._t = start or datetime(2024, 1, 1, 9, 0, 0)

    def next_quote(self, symbol: str) -> Quote:
        if symbol not in self._prices:
            raise KeyError(f"'{symbol}' 시작 가격이 설정되지 않았습니다.")
        prev = self._prices[symbol]
        shock = self._rng.uniform(-self._vol, self._vol)
        new_price = max(1.0, round(prev * (1.0 + shock), 2))
        self._prices[symbol] = new_price
        self._t += timedelta(seconds=1)
        return Quote(symbol=symbol, price=new_price, timestamp=self._t)
