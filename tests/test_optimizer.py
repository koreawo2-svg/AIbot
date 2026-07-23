from autotrader.optimizer import optimize


# 상승 후 급락하는 가격: 익절/손절 값에 따라 결과가 달라져야 함
PRICES = {"A": [100, 102, 105, 108, 112, 115, 118, 120,
                116, 110, 104, 100, 96, 92, 90.0]}


def test_optimize_varies_by_params():
    # 현금을 작게 잡아 포지션 손익이 총자산 수익률에 유의미하게 반영되도록 함
    base = {"target": 100, "qty": 10, "cash": 1500, "buy_logic": "OR"}
    grid = {"tp": [3, 5, 10], "sl": [2, 4], "trailing_stop_pct": [0, 3]}
    out = optimize(PRICES, base, grid, objective="return")

    # 3 * 2 * 2 = 12개 조합 평가
    assert out["evaluated"] == 12
    # 결과가 score 내림차순 정렬
    scores = [r["score"] for r in out["results"]]
    assert scores == sorted(scores, reverse=True)
    # 서로 다른 파라미터가 서로 다른 성과를 냄(익절/손절이 실제로 반영됨)
    returns = {r["stats"]["total_return_pct"] for r in out["results"]}
    assert len(returns) > 1


def test_optimize_params_keys_present():
    base = {"target": 100, "qty": 10, "buy_logic": "OR"}
    grid = {"tp": [3, 5], "sl": [2], "trailing_stop_pct": [0]}
    out = optimize(PRICES, base, grid)
    for r in out["results"]:
        assert set(r["params"].keys()) == {"tp", "sl", "trailing_stop_pct"}


def test_objective_winrate():
    base = {"target": 100, "qty": 10, "buy_logic": "OR"}
    grid = {"tp": [3, 5]}
    out = optimize(PRICES, base, grid, objective="winrate")
    assert out["objective"] == "winrate"
    # score가 승률과 일치
    for r in out["results"]:
        assert r["score"] == r["stats"]["win_rate_pct"]


def test_unknown_objective_raises():
    try:
        optimize(PRICES, {}, {"tp": [3]}, objective="sharpe")
        assert False, "예외가 발생해야 함"
    except ValueError:
        pass
