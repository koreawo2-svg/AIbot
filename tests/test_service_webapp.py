import json
import threading
import urllib.request

from http.server import ThreadingHTTPServer

from autotrader.service import result_to_dict, run_backtest
from autotrader import webapp


def test_run_backtest_and_serialize():
    prices = {"A": [100, 98, 96, 99, 103, 101, 105, 108, 104, 110.0]}
    result = run_backtest(prices, {"target": 100, "tp": 2, "sl": 3, "qty": 10, "buy_logic": "OR"})
    data = result_to_dict(result)
    assert set(data.keys()) == {"stats", "equity_curve", "trades"}
    assert "total_return_pct" in data["stats"]
    assert len(data["equity_curve"]) == 10


def test_randomwalk_series_deterministic():
    a = webapp._randomwalk_series(seed=7)
    b = webapp._randomwalk_series(seed=7)
    assert a == b
    assert len(a) == 200


def test_load_series_from_csv_text():
    payload = {"source": "csv", "symbol": "X",
               "csv_text": "Date,Close\n2024-01-02,100\n2024-01-03,110\n"}
    symbol, closes = webapp._load_series(payload)
    assert symbol == "X"
    assert closes == [100.0, 110.0]


def test_http_endpoint_end_to_end():
    server = ThreadingHTTPServer(("127.0.0.1", 0), webapp.Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        # GET / 은 HTML
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as r:
            assert r.status == 200
            assert b"AIbot" in r.read()

        # POST /api/backtest 는 JSON 결과
        body = json.dumps({
            "source": "sample", "symbol": "005930",
            "params": {"target": 70000, "tp": 3, "sl": 2, "qty": 100, "buy_logic": "OR"},
        }).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/backtest", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        assert data["ok"] is True
        assert data["symbol"] == "005930"
        assert "total_return_pct" in data["stats"]
    finally:
        server.shutdown()


def _post(port, path, obj):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
        return json.loads(r.read())


def test_live_monitor_end_to_end():
    import time
    server = ThreadingHTTPServer(("127.0.0.1", 0), webapp.Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        started = _post(port, "/api/live/start", {
            "symbol": "005930",
            "params": {"target": 70000, "tp": 3, "sl": 2, "qty": 100, "buy_logic": "OR"},
            "interval": 0.01, "ticks": 25, "start_price": 70000,
        })
        assert started["ok"] and started["started"]

        # 자연 종료까지 폴링
        state = {}
        for _ in range(200):
            state = _get(port, "/api/live/state")
            if not state["running"] and state["tick"] >= 0:
                break
            time.sleep(0.02)

        assert state["ok"] is True
        assert state["running"] is False
        assert len(state["equity_curve"]) >= 1
        assert "return_pct" in state
    finally:
        webapp.LIVE.stop()
        server.shutdown()
