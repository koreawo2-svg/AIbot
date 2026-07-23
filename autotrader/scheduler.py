"""실시간 자동매매 스케줄러(장중 루프).

일정 간격으로 엔진을 1스텝씩 돌려 자동 매수/매도를 수행한다.
지금은 PaperBroker + 실시간 시세 시뮬레이터로 '모의 실시간 매매'를 하지만,
broker만 실제 증권사 어댑터로 교체하면 그대로 실거래 루프가 된다.

의존성 주입(sleep_fn/clock_fn) 덕분에 테스트에서는 실제 대기 없이 검증할 수 있다.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable

from autotrader.brokers.paper import PaperBroker
from autotrader.engine import TradeRecord, TradingEngine


@dataclass
class TickSnapshot:
    """한 틱의 상태 스냅샷."""
    tick: int
    timestamp: float
    equity: float
    cash: float
    positions: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "timestamp": self.timestamp,
            "equity": round(self.equity, 2),
            "cash": round(self.cash, 2),
            "positions": self.positions,
            "trades": self.trades,
        }


class LiveTrader:
    """실시간(모의) 자동매매 루프."""

    def __init__(
        self,
        engine: TradingEngine,
        broker: PaperBroker,
        interval_sec: float = 1.0,
        state_file: str | None = None,
        on_tick: Callable[[TickSnapshot], None] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock_fn: Callable[[], float] = time.time,
    ):
        self._engine = engine
        self._broker = broker
        self._interval = interval_sec
        self._state_file = state_file
        self._on_tick = on_tick
        self._sleep = sleep_fn
        self._clock = clock_fn
        self._running = False
        self.snapshots: list[TickSnapshot] = []

    def stop(self) -> None:
        self._running = False

    def _snapshot(self, tick: int, records: list[TradeRecord]) -> TickSnapshot:
        account = self._broker.get_account()
        last = self._broker.last_prices()
        positions = []
        for sym, pos in account.positions.items():
            price = last.get(sym, pos.avg_price)
            positions.append({
                "symbol": sym,
                "quantity": pos.quantity,
                "avg_price": round(pos.avg_price, 2),
                "last_price": round(price, 2),
                "pnl_pct": round(pos.unrealized_pnl_pct(price), 2),
            })
        return TickSnapshot(
            tick=tick,
            timestamp=self._clock(),
            equity=self._broker.equity(),
            cash=account.cash,
            positions=positions,
            trades=[{
                "action": r.action, "symbol": r.symbol,
                "quantity": r.quantity, "price": round(r.price, 2), "reason": r.reason,
            } for r in records],
        )

    def _publish(self, snap: TickSnapshot) -> None:
        self.snapshots.append(snap)
        if self._state_file:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(snap.to_dict(), f, ensure_ascii=False)
        if self._on_tick:
            self._on_tick(snap)

    def run(self, ticks: int) -> list[TickSnapshot]:
        """지정한 틱 수만큼 실시간 루프 실행(틱 사이에 interval만큼 대기)."""
        self._engine.start()
        self._running = True
        for i in range(ticks):
            if not self._running:
                break
            records = self._engine.step()
            self._publish(self._snapshot(i, records))
            if i < ticks - 1 and self._running:
                self._sleep(self._interval)
        self._running = False
        return self.snapshots
