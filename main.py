"""자동매매 실행 진입점.

사용법:
    python main.py --demo                 # 내장 랜덤워크로 모의 매매 데모
    python main.py --config config.yaml   # 설정 파일로 실행

기본은 PaperBroker(모의). 실제 증권사 어댑터는 API 키 확보 후 연결한다.
"""
from __future__ import annotations

import argparse
import logging

from autotrader.brokers.paper import PaperBroker
from autotrader.engine import TradingEngine
from autotrader.market_data import RandomWalkFeed
from autotrader.models import OrderType
from autotrader.strategy.rule_engine import RuleEngineStrategy, SymbolRule


def build_demo() -> tuple[TradingEngine, PaperBroker]:
    """API 없이 바로 돌려보는 데모 구성."""
    rules = [
        SymbolRule(
            symbol="005930",           # 삼성전자(예시)
            target_buy_price=70000,
            order_quantity=10,
            take_profit_pct=3.0,
            stop_loss_pct=2.0,
            buy_logic="OR",            # 지정가 또는 지표
        ),
        SymbolRule(
            symbol="000660",           # SK하이닉스(예시)
            target_buy_price=120000,
            order_quantity=5,
            take_profit_pct=4.0,
            stop_loss_pct=2.5,
            buy_logic="AND",
        ),
    ]
    feed = RandomWalkFeed(
        start_prices={"005930": 72000, "000660": 125000},
        volatility=0.015,
        seed=7,
    )
    broker = PaperBroker(feed=feed, cash=10_000_000)
    strategy = RuleEngineStrategy(rules)
    engine = TradingEngine(
        broker=broker,
        strategy=strategy,
        symbols=[r.symbol for r in rules],
        order_type=OrderType.MARKET,
    )
    return engine, broker


def run_from_config(path: str) -> None:
    from autotrader.config import load_config

    cfg = load_config(path)
    if cfg.broker != "paper":
        raise SystemExit(
            f"'{cfg.broker}' 어댑터는 아직 구현 전입니다. 현재는 broker: paper 만 실행 가능합니다."
        )

    # 설정에 시작가가 없으면 목표매수가 기준으로 근사
    start_prices = {r.symbol: r.target_buy_price * 1.05 for r in cfg.rules}
    feed = RandomWalkFeed(start_prices=start_prices, seed=7)
    broker = PaperBroker(feed=feed, cash=cfg.cash)
    strategy = RuleEngineStrategy(cfg.rules)
    engine = TradingEngine(
        broker=broker,
        strategy=strategy,
        symbols=[r.symbol for r in cfg.rules],
        order_type=OrderType[cfg.order_type],
    )
    engine.run(cfg.steps)
    _print_summary(engine, broker)


def _print_summary(engine: TradingEngine, broker: PaperBroker) -> None:
    account = broker.get_account()
    print("\n===== 실행 요약 =====")
    print(f"체결/신호 건수: {len(engine.history)}")
    print(f"현금 잔고: {account.cash:,.0f}")
    for sym, pos in account.positions.items():
        print(f"보유 {sym}: {pos.quantity}주 @ 평단 {pos.avg_price:,.0f}")


def run_report(path: str, steps: int) -> None:
    """데모 구성으로 백테스트를 돌리고 HTML 리포트를 생성."""
    from autotrader.backtest import Backtester
    from autotrader.report import write_report

    engine, broker = build_demo()
    result = Backtester(engine, broker).run(steps)
    write_report(result, path)
    print(
        f"리포트 생성: {path}\n"
        f"  총 수익률 {result.total_return_pct:+.2f}% | "
        f"승률 {result.win_rate_pct:.0f}% | "
        f"MDD -{result.max_drawdown_pct:.2f}% | "
        f"체결 {len(result.trades)}건"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AIbot 자동 주식 매매(모의)")
    parser.add_argument("--config", help="설정 YAML 경로")
    parser.add_argument("--demo", action="store_true", help="내장 데모 실행")
    parser.add_argument("--steps", type=int, default=200, help="데모 반복 횟수")
    parser.add_argument("--report", metavar="OUT.html", help="백테스트 HTML 리포트 생성 경로")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.report:
        run_report(args.report, args.steps)
    elif args.config:
        run_from_config(args.config)
    else:
        # 기본은 데모
        engine, broker = build_demo()
        engine.run(args.steps)
        _print_summary(engine, broker)


if __name__ == "__main__":
    main()
