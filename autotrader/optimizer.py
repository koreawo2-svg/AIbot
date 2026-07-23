"""파라미터 그리드 탐색 최적화기.

익절/손절/트레일링스톱 등 여러 파라미터 조합을 모두 백테스트하고,
목표 지표(총수익률, 위험조정수익 등) 기준으로 순위를 매긴다.
"""
from __future__ import annotations

import itertools
from typing import Any, Callable

from autotrader.backtest import BacktestResult
from autotrader.service import run_backtest

# 조합 폭주 방지 상한
MAX_COMBOS = 2000


def _score_return(r: BacktestResult) -> float:
    return r.total_return_pct


def _score_return_dd(r: BacktestResult) -> float:
    """위험조정수익: 수익률 / (최대낙폭 + 1). 낙폭이 클수록 감점."""
    return r.total_return_pct / (r.max_drawdown_pct + 1.0)


def _score_winrate(r: BacktestResult) -> float:
    return r.win_rate_pct


OBJECTIVES: dict[str, Callable[[BacktestResult], float]] = {
    "return": _score_return,
    "return_dd": _score_return_dd,
    "winrate": _score_winrate,
}


def optimize(
    price_map: dict[str, list[float]],
    base_params: dict[str, Any],
    grid: dict[str, list[Any]],
    objective: str = "return",
    top: int = 20,
) -> dict[str, Any]:
    """grid의 모든 조합을 백테스트하고 순위를 반환.

    반환: {"objective", "evaluated", "capped", "results":[{params, score, stats}, ...]}
    results는 score 내림차순 정렬(최상위 top개).
    """
    if objective not in OBJECTIVES:
        raise ValueError(f"알 수 없는 objective: {objective} (가능: {list(OBJECTIVES)})")
    score_fn = OBJECTIVES[objective]

    keys = list(grid.keys())
    value_lists = [grid[k] for k in keys]
    combos = list(itertools.product(*value_lists)) if keys else [()]

    capped = len(combos) > MAX_COMBOS
    if capped:
        combos = combos[:MAX_COMBOS]

    results: list[dict[str, Any]] = []
    for combo in combos:
        params = dict(base_params)
        overrides = dict(zip(keys, combo))
        params.update(overrides)
        result = run_backtest(price_map, params)
        results.append({
            "params": overrides,
            "score": round(score_fn(result), 4),
            "stats": {
                "total_return_pct": round(result.total_return_pct, 2),
                "win_rate_pct": round(result.win_rate_pct, 1),
                "max_drawdown_pct": round(result.max_drawdown_pct, 2),
                "num_round_trips": result.num_round_trips,
                "num_trades": len(result.trades),
            },
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return {
        "objective": objective,
        "evaluated": len(results),
        "capped": capped,
        "results": results[:top],
    }
