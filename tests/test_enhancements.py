from datetime import datetime

from autotrader.models import Position, Quote
from autotrader.strategy import indicators
from autotrader.strategy.base import SignalType
from autotrader.strategy.rule_engine import RuleEngineStrategy, SymbolRule


def quote(symbol, price):
    return Quote(symbol=symbol, price=price, timestamp=datetime(2024, 1, 1))


def test_crossed_below():
    prices = [20.0] * 20 + [5.0]   # 20기간 SMA 하향 이탈
    assert indicators.crossed_below(prices, 20) is True
    assert indicators.crossed_below([20.0] * 21, 20) is False


def test_trailing_stop_triggers_sell():
    rule = SymbolRule(
        symbol="A", target_buy_price=100,
        take_profit_pct=100, stop_loss_pct=100,   # 익절/손절은 비켜두고
        trailing_stop_pct=5.0, use_rsi=False,
    )
    strat = RuleEngineStrategy([rule])
    pos = Position(symbol="A", quantity=10, avg_price=100)

    # 고점 120까지 상승(보유)
    assert strat.on_quote(quote("A", 110), pos).type == SignalType.HOLD
    assert strat.on_quote(quote("A", 120), pos).type == SignalType.HOLD
    # 고점 120 대비 -5%인 114 → 트레일링 스톱 발동
    sig = strat.on_quote(quote("A", 114), pos)
    assert sig.type == SignalType.SELL
    assert "트레일링" in sig.reason


def test_peak_resets_after_exit():
    rule = SymbolRule(symbol="A", target_buy_price=1000, trailing_stop_pct=5.0,
                      take_profit_pct=100, stop_loss_pct=100, use_rsi=False)
    strat = RuleEngineStrategy([rule])
    pos = Position(symbol="A", quantity=10, avg_price=100)
    strat.on_quote(quote("A", 130), pos)          # 고점 130 기록
    strat.on_quote(quote("A", 120), position=None)  # 청산됨 → 고점 리셋
    # 다시 매수 후 121이면 새 고점 기준이라 트레일링 미발동
    sig = strat.on_quote(quote("A", 121), pos)
    assert sig.type == SignalType.HOLD


def test_dead_cross_exit():
    rule = SymbolRule(symbol="A", target_buy_price=100, sma_period=20,
                      take_profit_pct=100, stop_loss_pct=100,
                      use_rsi=False, use_sma_cross_exit=True)
    strat = RuleEngineStrategy([rule])
    pos = Position(symbol="A", quantity=10, avg_price=100)
    # SMA 위에서 유지되다가 마지막에 급락 → 데드크로스
    for p in [20.0] * 20:
        strat.on_quote(quote("A", p), pos)
    sig = strat.on_quote(quote("A", 5.0), pos)
    assert sig.type == SignalType.SELL
    assert "데드크로스" in sig.reason
