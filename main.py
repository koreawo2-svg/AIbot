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


def run_csv(
    specs: list[str],
    report_path: str | None,
    target: float | None,
    tp: float,
    sl: float,
    qty: int,
    cash: float,
) -> None:
    """실제 과거 주가 CSV로 백테스트한다.

    specs: ["005930=samsung.csv", "000660=hynix.csv"] 형태.
    target 미지정 시 지표 기반 진입(가격조건은 항상 통과, buy_logic=AND).
    """
    from autotrader.backtest import Backtester
    from autotrader.data_loader import load_close_series
    from autotrader.market_data import ReplayFeed
    from autotrader.report import write_report
    from autotrader.strategy.rule_engine import RuleEngineStrategy, SymbolRule

    price_map: dict[str, list[float]] = {}
    rules: list[SymbolRule] = []
    date_range = ""
    for spec in specs:
        if "=" not in spec:
            raise SystemExit(f"--csv 형식 오류: '{spec}' (예: 005930=samsung.csv)")
        symbol, path = spec.split("=", 1)
        symbol, path = symbol.strip(), path.strip()
        dates, closes = load_close_series(path)
        price_map[symbol] = closes
        if dates and dates[0]:
            date_range = f"{dates[0]} ~ {dates[-1]}"
        # 목표가 미지정이면 매우 높게 잡아 '가격조건 항상 통과' → 지표가 진입을 결정
        buy_target = target if target is not None else max(closes) * 10
        buy_logic = "OR" if target is not None else "AND"
        rules.append(SymbolRule(
            symbol=symbol,
            target_buy_price=buy_target,
            order_quantity=qty,
            take_profit_pct=tp,
            stop_loss_pct=sl,
            buy_logic=buy_logic,
        ))
        print(f"로드: {symbol} <- {path} ({len(closes)}개, {date_range})")

    feed = ReplayFeed(price_map)
    broker = PaperBroker(feed=feed, cash=cash)
    strategy = RuleEngineStrategy(rules)
    engine = TradingEngine(
        broker=broker,
        strategy=strategy,
        symbols=list(price_map.keys()),
        order_type=OrderType.MARKET,
    )
    steps = max(len(p) for p in price_map.values())
    result = Backtester(engine, broker).run(steps)

    title = f"AIbot 백테스트 · {', '.join(price_map.keys())}"
    if date_range:
        title += f" ({date_range})"
    print(
        f"\n총 수익률 {result.total_return_pct:+.2f}% | "
        f"승률 {result.win_rate_pct:.0f}% | "
        f"MDD -{result.max_drawdown_pct:.2f}% | "
        f"체결 {len(result.trades)}건"
    )
    if report_path:
        write_report(result, report_path, title=title)
        print(f"리포트 생성: {report_path}")


def _parse_grid(spec: str) -> list[float]:
    """'2,3,4' -> [2.0, 3.0, 4.0]."""
    return [float(x) for x in spec.split(",") if x.strip() != ""]


def run_optimize(
    specs: list[str] | None,
    tp_grid: str,
    sl_grid: str,
    ts_grid: str,
    objective: str,
    target: float | None,
    qty: int,
    cash: float,
) -> None:
    """익절/손절/트레일링스톱 그리드를 자동 탐색해 최적 조합을 출력."""
    import os

    from autotrader.data_loader import load_close_series
    from autotrader.optimizer import optimize

    if specs:
        price_map: dict[str, list[float]] = {}
        for spec in specs:
            symbol, path = spec.split("=", 1)
            _, closes = load_close_series(path.strip())
            price_map[symbol.strip()] = closes
    else:
        sample = os.path.join(os.path.dirname(__file__), "data", "sample_005930.csv")
        _, closes = load_close_series(sample)
        price_map = {"005930": closes}

    base_params: dict = {"qty": qty, "cash": cash}
    if target is not None:
        base_params["target"] = target
        base_params["buy_logic"] = "OR"

    # 그리드 키는 service.build_rule 이 읽는 파라미터명(tp/sl/trailing_stop_pct)과 일치해야 함
    grid = {
        "tp": _parse_grid(tp_grid),
        "sl": _parse_grid(sl_grid),
        "trailing_stop_pct": _parse_grid(ts_grid),
    }
    out = optimize(price_map, base_params, grid, objective=objective, top=10)

    print(f"\n최적화 결과 (목표={out['objective']}, 평가 {out['evaluated']}개 조합)")
    if out["capped"]:
        print("  ※ 조합이 많아 상한까지만 평가했습니다.")
    print(f"{'순위':>3} {'익절%':>6} {'손절%':>6} {'트레일%':>7} {'수익률':>8} {'승률':>6} {'MDD':>7} {'체결':>5}")
    for i, r in enumerate(out["results"], 1):
        p, s = r["params"], r["stats"]
        print(
            f"{i:>3} {p['tp']:>6.1f} {p['sl']:>6.1f} "
            f"{p['trailing_stop_pct']:>7.1f} {s['total_return_pct']:>7.2f}% "
            f"{s['win_rate_pct']:>5.0f}% {s['max_drawdown_pct']:>6.2f}% {s['num_trades']:>5}"
        )
    if out["results"]:
        best = out["results"][0]
        print(f"\n▶ 추천 조합: {best['params']} → 수익률 {best['stats']['total_return_pct']:+.2f}%")


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
    parser.add_argument("--csv", action="append", metavar="SYMBOL=PATH",
                        help="실제 과거 주가 CSV로 백테스트 (반복 지정 가능)")
    parser.add_argument("--target", type=float, help="목표 매수가(미지정 시 지표 기반 진입)")
    parser.add_argument("--tp", type=float, default=5.0, help="익절 %% (기본 5)")
    parser.add_argument("--sl", type=float, default=3.0, help="손절 %% (기본 3)")
    parser.add_argument("--qty", type=int, default=10, help="1회 주문 수량(기본 10)")
    parser.add_argument("--cash", type=float, default=10_000_000, help="시작 현금")
    parser.add_argument("--optimize", action="store_true", help="익절/손절/트레일링 그리드 자동 최적화")
    parser.add_argument("--tp-grid", default="2,3,4,5", help="익절 후보(콤마): 예 2,3,4,5")
    parser.add_argument("--sl-grid", default="1,2,3", help="손절 후보(콤마)")
    parser.add_argument("--ts-grid", default="0,3,5", help="트레일링스톱 후보(콤마, 0=미사용)")
    parser.add_argument("--objective", default="return",
                        choices=["return", "return_dd", "winrate"], help="최적화 목표")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.optimize:
        run_optimize(args.csv, args.tp_grid, args.sl_grid, args.ts_grid,
                     args.objective, args.target, args.qty, args.cash)
    elif args.csv:
        run_csv(args.csv, args.report, args.target, args.tp, args.sl, args.qty, args.cash)
    elif args.report:
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
