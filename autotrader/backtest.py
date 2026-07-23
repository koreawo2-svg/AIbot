"""백테스트 실행기.

엔진을 한 스텝씩 돌리면서 평가금액(equity) 곡선과 매매 내역을 기록하고,
수익률/승률/최대낙폭(MDD) 등 요약 통계를 계산한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from autotrader.brokers.paper import PaperBroker
from autotrader.engine import TradeRecord, TradingEngine


@dataclass
class BacktestResult:
    start_equity: float
    equity_curve: list[float] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)

    @property
    def end_equity(self) -> float:
        return self.equity_curve[-1] if self.equity_curve else self.start_equity

    @property
    def total_return_pct(self) -> float:
        if self.start_equity == 0:
            return 0.0
        return (self.end_equity - self.start_equity) / self.start_equity * 100.0

    @property
    def max_drawdown_pct(self) -> float:
        """최대 낙폭(고점 대비 최대 하락률, %)."""
        peak = self.start_equity
        mdd = 0.0
        for eq in self.equity_curve:
            peak = max(peak, eq)
            if peak > 0:
                dd = (peak - eq) / peak * 100.0
                mdd = max(mdd, dd)
        return mdd

    def _round_trips(self) -> list[float]:
        """매수→매도 한 사이클의 손익률(%) 목록. 승률 계산용."""
        results: list[float] = []
        entry: dict[str, float] = {}
        for t in self.trades:
            if t.price <= 0 or t.quantity <= 0:
                continue
            if t.action.startswith("BUY"):
                entry[t.symbol] = t.price
            elif t.action.startswith("SELL") and t.symbol in entry:
                buy = entry.pop(t.symbol)
                if buy > 0:
                    results.append((t.price - buy) / buy * 100.0)
        return results

    @property
    def win_rate_pct(self) -> float:
        rts = self._round_trips()
        if not rts:
            return 0.0
        wins = sum(1 for r in rts if r > 0)
        return wins / len(rts) * 100.0

    @property
    def num_round_trips(self) -> int:
        return len(self._round_trips())


class Backtester:
    """PaperBroker + 엔진으로 스텝 단위 백테스트를 수행."""

    def __init__(self, engine: TradingEngine, broker: PaperBroker):
        self._engine = engine
        self._broker = broker

    def run(self, steps: int) -> BacktestResult:
        self._engine.start()
        start_equity = self._broker.equity() or self._broker.get_account().cash
        result = BacktestResult(start_equity=start_equity)
        for _ in range(steps):
            self._engine.step()
            result.equity_curve.append(self._broker.equity())
        result.trades = list(self._engine.history)
        return result
