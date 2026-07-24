import pytest

from autotrader.brokers.kiwoom import KiwoomBroker, _parse_price
from autotrader.models import Order, OrderType, Side


class FakeHttp:
    """http_post 대역: 호출을 기록하고 미리 준비한 응답을 순서대로 반환."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append({"url": url, "headers": headers, "body": body})
        return self._responses.pop(0)


def test_parse_price_variants():
    assert _parse_price("+70000") == 70000.0
    assert _parse_price("-1,250") == 1250.0
    assert _parse_price("70000") == 70000.0
    assert _parse_price("") == 0.0
    assert _parse_price(None) == 0.0


def test_connect_uses_mock_base_and_stores_token():
    http = FakeHttp([(200, {"token": "TKN", "token_type": "bearer"})])
    b = KiwoomBroker("k", "s", "123-45", paper=True, http_post=http)
    b.connect()
    call = http.calls[0]
    assert call["url"] == "https://mockapi.kiwoom.com/oauth2/token"
    assert call["body"] == {"grant_type": "client_credentials", "appkey": "k", "secretkey": "s"}
    assert b._token == "TKN"


def test_connect_failure_raises():
    http = FakeHttp([(401, {"return_msg": "invalid key"})])
    b = KiwoomBroker("k", "s", "123-45", http_post=http)
    with pytest.raises(RuntimeError):
        b.connect()


def test_real_base_when_not_paper():
    http = FakeHttp([(200, {"token": "T"})])
    b = KiwoomBroker("k", "s", "1", paper=False, http_post=http)
    b.connect()
    assert http.calls[0]["url"].startswith("https://api.kiwoom.com")


def test_get_quote_parses_current_price():
    http = FakeHttp([
        (200, {"token": "T"}),
        (200, {"return_code": 0, "cur_prc": "-70,500"}),
    ])
    b = KiwoomBroker("k", "s", "1", http_post=http)
    b.connect()
    q = b.get_quote("005930")
    assert q.symbol == "005930"
    assert q.price == 70500.0
    # 시세 요청 헤더에 api-id / bearer 토큰이 실렸는지
    quote_call = http.calls[1]
    assert quote_call["url"] == "https://mockapi.kiwoom.com/api/dostk/stkinfo"
    assert quote_call["headers"]["api-id"] == "ka10001"
    assert quote_call["headers"]["authorization"] == "Bearer T"
    assert quote_call["body"] == {"stk_cd": "005930"}


def test_market_buy_order_request():
    http = FakeHttp([
        (200, {"token": "T"}),
        (200, {"return_code": 0, "ord_no": "0001"}),
    ])
    b = KiwoomBroker("k", "s", "1", http_post=http)
    b.connect()
    order = Order("005930", Side.BUY, 10, OrderType.MARKET)
    result = b.place_order(order)
    call = http.calls[1]
    assert call["url"] == "https://mockapi.kiwoom.com/api/dostk/ordr"
    assert call["headers"]["api-id"] == "kt10000"      # 매수
    assert call["body"]["stk_cd"] == "005930"
    assert call["body"]["ord_qty"] == "10"
    assert call["body"]["trde_tp"] == "3"              # 시장가
    assert result.order_id == "0001"


def test_limit_sell_order_request():
    http = FakeHttp([
        (200, {"token": "T"}),
        (200, {"return_code": 0, "ord_no": "0002"}),
    ])
    b = KiwoomBroker("k", "s", "1", http_post=http)
    b.connect()
    order = Order("000660", Side.SELL, 5, OrderType.LIMIT, limit_price=120000)
    b.place_order(order)
    call = http.calls[1]
    assert call["headers"]["api-id"] == "kt10001"      # 매도
    assert call["body"]["trde_tp"] == "0"              # 지정가(보통)
    assert call["body"]["ord_uv"] == "120000"


def test_api_return_code_error_raises():
    http = FakeHttp([
        (200, {"token": "T"}),
        (200, {"return_code": 3, "return_msg": "잔고부족"}),
    ])
    b = KiwoomBroker("k", "s", "1", http_post=http)
    b.connect()
    with pytest.raises(RuntimeError, match="잔고부족"):
        b.get_quote("005930")


def test_calls_before_connect_raise():
    b = KiwoomBroker("k", "s", "1", http_post=FakeHttp([]))
    with pytest.raises(RuntimeError, match="connect"):
        b.get_quote("005930")
