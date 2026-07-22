from datetime import datetime

from autotrader.models import Position, Quote
from autotrader.strategy.base import SignalType
from autotrader.strategy.rule_engine import RuleEngineStrategy, SymbolRule


def quote(symbol, price):
    return Quote(symbol=symbol, price=price, timestamp=datetime(2024, 1, 1))


def test_buy_on_target_price_or_logic():
    rule = SymbolRule(
        symbol="A", target_buy_price=100, order_quantity=5,
        use_rsi=False, use_sma_cross=False, buy_logic="OR",
    )
    strat = RuleEngineStrategy([rule])
    # 현재가 <= 목표가 → 매수
    sig = strat.on_quote(quote("A", 95), position=None)
    assert sig.type == SignalType.BUY
    assert sig.quantity == 5


def test_no_buy_above_target_with_and_logic():
    rule = SymbolRule(
        symbol="A", target_buy_price=100,
        use_rsi=False, use_sma_cross=False, buy_logic="AND",
    )
    strat = RuleEngineStrategy([rule])
    sig = strat.on_quote(quote("A", 110), position=None)
    assert sig.type == SignalType.HOLD


def test_take_profit_triggers_sell():
    rule = SymbolRule(symbol="A", target_buy_price=100, take_profit_pct=5.0)
    strat = RuleEngineStrategy([rule])
    pos = Position(symbol="A", quantity=10, avg_price=100)
    # +6% → 익절
    sig = strat.on_quote(quote("A", 106), position=pos)
    assert sig.type == SignalType.SELL
    assert sig.quantity == 10
    assert "익절" in sig.reason


def test_stop_loss_triggers_sell():
    rule = SymbolRule(symbol="A", target_buy_price=100, stop_loss_pct=3.0)
    strat = RuleEngineStrategy([rule])
    pos = Position(symbol="A", quantity=10, avg_price=100)
    # -4% → 손절
    sig = strat.on_quote(quote("A", 96), position=pos)
    assert sig.type == SignalType.SELL
    assert "손절" in sig.reason


def test_hold_when_within_bands():
    rule = SymbolRule(
        symbol="A", target_buy_price=100, take_profit_pct=5.0, stop_loss_pct=3.0,
        use_rsi=False,
    )
    strat = RuleEngineStrategy([rule])
    pos = Position(symbol="A", quantity=10, avg_price=100)
    sig = strat.on_quote(quote("A", 101), position=pos)
    assert sig.type == SignalType.HOLD
