"""기술적 지표 계산.

가격 시계열(list[float])을 입력받아 지표 값을 반환한다.
데이터가 부족하면 None을 반환한다.
"""
from __future__ import annotations


def sma(prices: list[float], period: int) -> float | None:
    """단순이동평균(Simple Moving Average)."""
    if period <= 0 or len(prices) < period:
        return None
    window = prices[-period:]
    return sum(window) / period


def rsi(prices: list[float], period: int = 14) -> float | None:
    """RSI(Relative Strength Index), 0~100.

    period+1개 이상의 가격이 있어야 계산 가능하다.
    """
    if period <= 0 or len(prices) < period + 1:
        return None

    gains = 0.0
    losses = 0.0
    # 최근 period개의 가격 변화를 사용
    recent = prices[-(period + 1):]
    for prev, cur in zip(recent, recent[1:]):
        change = cur - prev
        if change >= 0:
            gains += change
        else:
            losses -= change

    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def crossed_above(prices: list[float], period: int) -> bool:
    """직전 봉에서 이동평균 아래였다가 현재 위로 돌파했는지(골든크로스 성격)."""
    if len(prices) < period + 1:
        return False
    prev_sma = sma(prices[:-1], period)
    cur_sma = sma(prices, period)
    if prev_sma is None or cur_sma is None:
        return False
    return prices[-2] <= prev_sma and prices[-1] > cur_sma
