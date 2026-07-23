import json

from autotrader.brokers.paper import PaperBroker
from autotrader.engine import TradingEngine
from autotrader.market_data import ReplayFeed
from autotrader.models import OrderType
from autotrader.scheduler import LiveTrader
from autotrader.strategy.rule_engine import RuleEngineStrategy, SymbolRule


def build(prices):
    feed = ReplayFeed({"A": prices})
    broker = PaperBroker(feed=feed, cash=100_000, fee_rate=0.0, tax_rate=0.0)
    rule = SymbolRule(symbol="A", target_buy_price=100, order_quantity=10,
                      take_profit_pct=3, stop_loss_pct=3, use_rsi=False,
                      use_sma_cross=False, buy_logic="OR")
    engine = TradingEngine(broker, RuleEngineStrategy([rule]), ["A"], OrderType.MARKET)
    return engine, broker


def test_runs_all_ticks_without_real_sleep():
    engine, broker = build([100, 101, 104, 103, 100.0])
    sleeps = []
    trader = LiveTrader(engine, broker, interval_sec=5.0,
                        sleep_fn=lambda s: sleeps.append(s),
                        clock_fn=lambda: 0.0)
    snaps = trader.run(5)
    assert len(snaps) == 5
    # 틱 사이에만 대기(마지막 틱 뒤에는 대기 없음)
    assert sleeps == [5.0, 5.0, 5.0, 5.0]
    assert all(s.tick == i for i, s in enumerate(snaps))


def test_snapshot_tracks_position_and_trades():
    engine, broker = build([100, 104.0])   # 100에 매수 → 104(+4%)에 익절
    trader = LiveTrader(engine, broker, sleep_fn=lambda s: None, clock_fn=lambda: 0.0)
    snaps = trader.run(2)
    # 첫 틱: 매수 발생
    assert any(t["action"].startswith("BUY") for t in snaps[0].trades)
    # 둘째 틱: 익절 매도 발생, 보유 없음
    assert any(t["action"].startswith("SELL") for t in snaps[1].trades)
    assert snaps[1].positions == []


def test_state_file_written(tmp_path):
    engine, broker = build([100, 101.0])
    path = tmp_path / "state.json"
    trader = LiveTrader(engine, broker, state_file=str(path),
                        sleep_fn=lambda s: None, clock_fn=lambda: 123.0)
    trader.run(2)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tick"] == 1
    assert data["timestamp"] == 123.0
    assert "equity" in data and "positions" in data


def test_stop_halts_loop():
    engine, broker = build([100, 101, 102, 103, 104.0])
    trader = LiveTrader(engine, broker, sleep_fn=lambda s: None, clock_fn=lambda: 0.0)

    # on_tick 콜백에서 2틱 후 중단
    def stopper(snap):
        if snap.tick == 1:
            trader.stop()
    trader._on_tick = stopper
    snaps = trader.run(5)
    assert len(snaps) == 2
