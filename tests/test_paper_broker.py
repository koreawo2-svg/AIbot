from autotrader.brokers.paper import PaperBroker
from autotrader.market_data import ReplayFeed
from autotrader.models import Order, OrderType, Side


def make_broker(prices, cash=1_000_000):
    feed = ReplayFeed({"A": prices})
    return PaperBroker(feed=feed, cash=cash, fee_rate=0.0, tax_rate=0.0)


def test_market_buy_reduces_cash_and_adds_position():
    broker = make_broker([100.0])
    broker.get_quote("A")
    order = Order("A", Side.BUY, 10, OrderType.MARKET)
    result = broker.place_order(order)

    assert result.status.value == "FILLED"
    assert result.filled_quantity == 10
    acct = broker.get_account()
    assert acct.cash == 1_000_000 - 100 * 10
    assert acct.positions["A"].quantity == 10


def test_buy_rejected_when_insufficient_cash():
    broker = make_broker([100.0], cash=500)
    broker.get_quote("A")
    result = broker.place_order(Order("A", Side.BUY, 10, OrderType.MARKET))
    assert result.status.value == "REJECTED"


def test_sell_realizes_cash():
    broker = make_broker([100.0, 120.0])
    broker.get_quote("A")
    broker.place_order(Order("A", Side.BUY, 10, OrderType.MARKET))
    broker.get_quote("A")  # 가격 120으로 이동
    result = broker.place_order(Order("A", Side.SELL, 10, OrderType.MARKET))

    assert result.status.value == "FILLED"
    acct = broker.get_account()
    assert "A" not in acct.positions
    # 100에 사서 120에 팔았으므로 현금 증가
    assert acct.cash == 1_000_000 - 1000 + 1200


def test_limit_buy_not_filled_above_limit():
    broker = make_broker([100.0])
    broker.get_quote("A")
    order = Order("A", Side.BUY, 1, OrderType.LIMIT, limit_price=90.0)
    result = broker.place_order(order)
    # 현재가 100 > 지정가 90 → 미체결
    assert result.status.value == "PENDING"


def test_limit_buy_filled_at_or_below_limit():
    broker = make_broker([90.0])
    broker.get_quote("A")
    order = Order("A", Side.BUY, 1, OrderType.LIMIT, limit_price=90.0)
    result = broker.place_order(order)
    assert result.status.value == "FILLED"
