from autotrader.strategy import indicators


def test_sma_basic():
    assert indicators.sma([1, 2, 3, 4, 5], 5) == 3
    assert indicators.sma([1, 2, 3, 4, 5], 2) == 4.5


def test_sma_insufficient_data():
    assert indicators.sma([1, 2], 5) is None
    assert indicators.sma([], 3) is None


def test_rsi_all_gains_is_100():
    prices = [float(i) for i in range(1, 20)]  # 계속 상승
    assert indicators.rsi(prices, 14) == 100.0


def test_rsi_range():
    prices = [10, 11, 10.5, 11.2, 10.8, 11.5, 11.1, 11.8,
              11.4, 12.0, 11.6, 12.2, 11.9, 12.5, 12.1]
    val = indicators.rsi(prices, 14)
    assert val is not None
    assert 0.0 <= val <= 100.0


def test_rsi_insufficient_data():
    assert indicators.rsi([1, 2, 3], 14) is None


def test_crossed_above():
    # 20기간 SMA를 상향 돌파하는 시퀀스
    prices = [10.0] * 20 + [15.0]
    assert indicators.crossed_above(prices, 20) is True
    # 계속 아래면 False
    assert indicators.crossed_above([10.0] * 21, 20) is False
