from autotrader.backtest import BacktestResult
from autotrader.engine import TradeRecord


def make_result(equity, trades=None):
    r = BacktestResult(start_equity=equity[0])
    r.equity_curve = equity
    r.trades = trades or []
    return r


def test_total_return_pct():
    r = make_result([100.0, 110.0])
    assert round(r.total_return_pct, 2) == 10.0


def test_max_drawdown():
    # 100 -> 120 -> 90 : 고점 120 대비 90 이면 -25%
    r = make_result([100.0, 120.0, 90.0, 100.0])
    assert round(r.max_drawdown_pct, 2) == 25.0


def test_win_rate_and_round_trips():
    trades = [
        TradeRecord("A", "BUY/FILLED", 1, 100.0, ""),
        TradeRecord("A", "SELL/FILLED", 1, 110.0, ""),   # +10% 승
        TradeRecord("A", "BUY/FILLED", 1, 100.0, ""),
        TradeRecord("A", "SELL/FILLED", 1, 95.0, ""),    # -5% 패
    ]
    r = make_result([1_000_000.0, 1_000_500.0], trades)
    assert r.num_round_trips == 2
    assert r.win_rate_pct == 50.0


def test_empty_curve_defaults():
    r = BacktestResult(start_equity=1000.0)
    assert r.end_equity == 1000.0
    assert r.total_return_pct == 0.0
    assert r.max_drawdown_pct == 0.0
    assert r.win_rate_pct == 0.0
