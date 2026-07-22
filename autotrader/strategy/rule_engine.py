"""지정가 + 지표를 조합한 규칙 기반 전략.

매수 판단(미보유 시):
  - 가격 조건: 현재가 <= 목표매수가(target_buy_price)
  - 지표 조건: RSI 과매도(rsi < rsi_oversold) 또는 이동평균 상향돌파
  - 두 조건을 buy_logic("AND"/"OR")으로 결합

매도 판단(보유 시, 아래 중 하나라도 만족하면 매도 = 리스크 관리 우선):
  - 익절: 평가손익률 >= take_profit_pct
  - 손절: 평가손익률 <= -stop_loss_pct
  - 지표: RSI 과매수(rsi > rsi_overbought)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from autotrader.models import Position, Quote
from autotrader.strategy import indicators
from autotrader.strategy.base import Signal, SignalType, Strategy


@dataclass
class SymbolRule:
    """종목별 전략 파라미터."""
    symbol: str
    target_buy_price: float          # 지정 목표 매수가
    order_quantity: int = 1          # 1회 주문 수량
    take_profit_pct: float = 5.0     # 익절 기준(%)
    stop_loss_pct: float = 3.0       # 손절 기준(%)
    # 지표 파라미터
    sma_period: int = 20
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    use_sma_cross: bool = True
    use_rsi: bool = True
    # 매수 시 가격조건과 지표조건 결합 방식
    buy_logic: str = "AND"           # "AND" 또는 "OR"


class RuleEngineStrategy(Strategy):
    """종목별 규칙을 적용하는 전략."""

    def __init__(self, rules: list[SymbolRule], history_limit: int = 500):
        self._rules: dict[str, SymbolRule] = {r.symbol: r for r in rules}
        self._history: dict[str, list[float]] = {r.symbol: [] for r in rules}
        self._history_limit = history_limit

    def on_quote(self, quote: Quote, position: Position | None) -> Signal:
        rule = self._rules.get(quote.symbol)
        if rule is None:
            return Signal(quote.symbol, SignalType.HOLD, reason="규칙 없음")

        prices = self._history.setdefault(quote.symbol, [])
        prices.append(quote.price)
        if len(prices) > self._history_limit:
            del prices[0]

        if position and position.quantity > 0:
            return self._evaluate_sell(rule, quote, position, prices)
        return self._evaluate_buy(rule, quote, prices)

    # --- 매수 ---
    def _evaluate_buy(self, rule: SymbolRule, quote: Quote, prices: list[float]) -> Signal:
        price_ok = quote.price <= rule.target_buy_price

        indicator_ok, ind_reason = self._buy_indicator_ok(rule, prices)

        if rule.buy_logic.upper() == "OR":
            triggered = price_ok or indicator_ok
        else:  # 기본 AND
            triggered = price_ok and indicator_ok

        if triggered:
            reason = f"매수(가격≤{rule.target_buy_price}:{price_ok}, 지표:{ind_reason}, logic={rule.buy_logic})"
            return Signal(rule.symbol, SignalType.BUY, rule.order_quantity, reason)
        return Signal(rule.symbol, SignalType.HOLD, reason="매수조건 미충족")

    def _buy_indicator_ok(self, rule: SymbolRule, prices: list[float]) -> tuple[bool, str]:
        """지표 매수 조건. 사용하는 지표가 하나라도 참이면 True."""
        reasons: list[str] = []
        ok = False

        if rule.use_rsi:
            r = indicators.rsi(prices, rule.rsi_period)
            if r is not None and r < rule.rsi_oversold:
                ok = True
                reasons.append(f"RSI={r:.1f}<{rule.rsi_oversold}")
            elif r is not None:
                reasons.append(f"RSI={r:.1f}")

        if rule.use_sma_cross:
            if indicators.crossed_above(prices, rule.sma_period):
                ok = True
                reasons.append("SMA상향돌파")

        # 지표를 아무것도 사용하지 않으면 지표조건은 통과로 간주(순수 지정가 매매)
        if not rule.use_rsi and not rule.use_sma_cross:
            return True, "지표미사용"

        return ok, ",".join(reasons) if reasons else "데이터부족"

    # --- 매도 ---
    def _evaluate_sell(
        self, rule: SymbolRule, quote: Quote, position: Position, prices: list[float]
    ) -> Signal:
        pnl = position.unrealized_pnl_pct(quote.price)
        qty = position.quantity

        if pnl >= rule.take_profit_pct:
            return Signal(rule.symbol, SignalType.SELL, qty, f"익절 pnl={pnl:.2f}%")
        if pnl <= -rule.stop_loss_pct:
            return Signal(rule.symbol, SignalType.SELL, qty, f"손절 pnl={pnl:.2f}%")

        if rule.use_rsi:
            r = indicators.rsi(prices, rule.rsi_period)
            if r is not None and r > rule.rsi_overbought:
                return Signal(rule.symbol, SignalType.SELL, qty, f"RSI과매수={r:.1f}")

        return Signal(rule.symbol, SignalType.HOLD, reason=f"보유 pnl={pnl:.2f}%")
