"""백테스트 서비스 계층.

CLI/웹 UI가 공통으로 쓰는 실행 함수. 가격 시계열 + 전략 파라미터를 받아
BacktestResult를 만들고, JSON 직렬화용 dict로 변환한다.
"""
from __future__ import annotations

from typing import Any

from autotrader.backtest import Backtester, BacktestResult
from autotrader.brokers.paper import PaperBroker
from autotrader.engine import TradingEngine
from autotrader.market_data import ReplayFeed
from autotrader.models import OrderType
from autotrader.strategy.rule_engine import RuleEngineStrategy, SymbolRule


def build_rule(symbol: str, closes: list[float], params: dict[str, Any]) -> SymbolRule:
    """파라미터 dict로 SymbolRule 생성. target 미지정이면 지표 기반 진입."""
    target = params.get("target")
    if target is None:
        buy_target = max(closes) * 10 if closes else 1e12
        buy_logic = "AND"
    else:
        buy_target = float(target)
        buy_logic = str(params.get("buy_logic", "OR"))

    return SymbolRule(
        symbol=symbol,
        target_buy_price=buy_target,
        order_quantity=int(params.get("qty", 10)),
        take_profit_pct=float(params.get("tp", 5.0)),
        stop_loss_pct=float(params.get("sl", 3.0)),
        sma_period=int(params.get("sma_period", 20)),
        rsi_period=int(params.get("rsi_period", 14)),
        rsi_oversold=float(params.get("rsi_oversold", 30.0)),
        rsi_overbought=float(params.get("rsi_overbought", 70.0)),
        use_sma_cross=bool(params.get("use_sma_cross", True)),
        use_rsi=bool(params.get("use_rsi", True)),
        buy_logic=buy_logic,
        trailing_stop_pct=float(params.get("trailing_stop_pct", 0.0)),
        use_sma_cross_exit=bool(params.get("use_sma_cross_exit", False)),
    )


def run_backtest(price_map: dict[str, list[float]], params: dict[str, Any]) -> BacktestResult:
    """가격 시계열 맵과 파라미터로 백테스트 실행."""
    if not price_map:
        raise ValueError("가격 데이터가 비어 있습니다.")
    rules = [build_rule(sym, closes, params) for sym, closes in price_map.items()]
    feed = ReplayFeed(price_map)
    broker = PaperBroker(feed=feed, cash=float(params.get("cash", 10_000_000)))
    strategy = RuleEngineStrategy(rules)
    engine = TradingEngine(
        broker=broker,
        strategy=strategy,
        symbols=list(price_map.keys()),
        order_type=OrderType.MARKET,
    )
    steps = max(len(p) for p in price_map.values())
    return Backtester(engine, broker).run(steps)


def result_to_dict(result: BacktestResult) -> dict[str, Any]:
    """BacktestResult를 JSON 직렬화 가능한 dict로 변환."""
    return {
        "stats": {
            "start_equity": round(result.start_equity, 2),
            "end_equity": round(result.end_equity, 2),
            "total_return_pct": round(result.total_return_pct, 2),
            "win_rate_pct": round(result.win_rate_pct, 1),
            "max_drawdown_pct": round(result.max_drawdown_pct, 2),
            "num_round_trips": result.num_round_trips,
            "num_trades": len(result.trades),
        },
        "equity_curve": [round(e, 2) for e in result.equity_curve],
        "trades": [
            {
                "action": t.action,
                "symbol": t.symbol,
                "quantity": t.quantity,
                "price": round(t.price, 2),
                "reason": t.reason,
            }
            for t in result.trades
        ],
    }
