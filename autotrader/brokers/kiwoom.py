"""키움증권 REST API 어댑터.

키움 신규 REST API(크로스플랫폼)를 사용한다. 구 OpenAPI+(OCX, Windows 32bit)가
아니라, APP KEY/SECRET으로 토큰을 발급받아 HTTP로 주문/조회하는 방식이다.

사양(공식 포털/커뮤니티 확인):
  - Base URL   실전 https://api.kiwoom.com  /  모의 https://mockapi.kiwoom.com
  - 토큰       POST /oauth2/token  body {grant_type:"client_credentials", appkey, secretkey}
  - 시세       POST /api/dostk/stkinfo   api-id ka10001 (주식기본정보요청)
  - 잔고       POST /api/dostk/acnt      api-id kt00004 (계좌평가현황요청)
  - 매수/매도  POST /api/dostk/ordr      api-id kt10000 / kt10001
  - 헤더       authorization: Bearer <token>, api-id, cont-yn, next-key

⚠️ 주의
  1) 반드시 paper=True(모의투자, mockapi)로 충분히 검증한 뒤 실계좌에 붙일 것.
  2) 응답 필드명(cur_prc, 잔고 항목 등)은 계정/버전에 따라 다를 수 있으니
     모의투자로 실제 응답을 한 번 확인하고 _FIELD 매핑을 조정할 것.
  3) APP KEY/SECRET은 절대 커밋하지 말 것(.env / 환경변수 사용).
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from autotrader.brokers.base import BrokerAdapter
from autotrader.models import (
    Account,
    Order,
    OrderStatus,
    OrderType,
    Position,
    Quote,
    Side,
)

# HTTP 전송 계층: (url, headers, json_body) -> (status_code, response_dict)
HttpPost = Callable[[str, dict, dict], tuple[int, dict]]


def _default_http_post(url: str, headers: dict, body: dict) -> tuple[int, dict]:
    import requests  # 지연 임포트(테스트/모의는 requests 불필요)

    resp = requests.post(url, headers=headers, json=body, timeout=10)
    try:
        data = resp.json()
    except ValueError:
        data = {"_raw": resp.text}
    return resp.status_code, data


def _parse_price(raw) -> float:
    """키움 가격 필드('+70000', '-1,250', '70000' 등)를 양수 float으로 변환."""
    if raw is None:
        return 0.0
    s = str(raw).strip().replace(",", "")
    if s in ("", "+", "-"):
        return 0.0
    # 부호는 등락 방향 표시일 뿐 가격은 절대값
    if s[0] in "+-":
        s = s[1:]
    try:
        return abs(float(s))
    except ValueError:
        return 0.0


class KiwoomBroker(BrokerAdapter):
    """키움증권 REST API 연동."""

    name = "kiwoom"

    REAL_BASE = "https://api.kiwoom.com"
    MOCK_BASE = "https://mockapi.kiwoom.com"

    # 엔드포인트 경로
    PATH_TOKEN = "/oauth2/token"
    PATH_QUOTE = "/api/dostk/stkinfo"
    PATH_ACCOUNT = "/api/dostk/acnt"
    PATH_ORDER = "/api/dostk/ordr"

    # TR(api-id)
    TR_QUOTE = "ka10001"     # 주식기본정보요청
    TR_ACCOUNT = "kt00004"   # 계좌평가현황요청
    TR_BUY = "kt10000"       # 주식매수주문
    TR_SELL = "kt10001"      # 주식매도주문

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_no: str,
        *,
        paper: bool = True,
        exchange: str = "KRX",
        http_post: HttpPost | None = None,
    ):
        self._app_key = app_key
        self._app_secret = app_secret
        self._account_no = account_no
        self._paper = paper
        self._exchange = exchange
        self._base = self.MOCK_BASE if paper else self.REAL_BASE
        self._http_post = http_post or _default_http_post
        self._token: str | None = None
        self._last_quotes: dict[str, Quote] = {}

    # --- 연결 ---
    def connect(self) -> None:
        status, data = self._http_post(
            self._base + self.PATH_TOKEN,
            {"Content-Type": "application/json;charset=UTF-8"},
            {
                "grant_type": "client_credentials",
                "appkey": self._app_key,
                "secretkey": self._app_secret,
            },
        )
        if status != 200 or not data.get("token"):
            msg = data.get("return_msg") or data.get("_raw") or "토큰 발급 실패"
            raise RuntimeError(f"키움 토큰 발급 실패(status={status}): {msg}")
        self._token = data["token"]

    def disconnect(self) -> None:
        self._token = None

    # --- 공통 요청 ---
    def _api(self, path: str, api_id: str, body: dict) -> dict:
        if not self._token:
            raise RuntimeError("먼저 connect()로 토큰을 발급받아야 합니다.")
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {self._token}",
            "api-id": api_id,
            "cont-yn": "N",
            "next-key": "",
        }
        status, data = self._http_post(self._base + path, headers, body)
        if status != 200:
            raise RuntimeError(f"키움 API 오류(status={status}, api-id={api_id}): {data}")
        # 키움 공통 응답코드: return_code 0 == 정상
        rc = data.get("return_code")
        if rc not in (0, None):
            raise RuntimeError(
                f"키움 API 실패(api-id={api_id}, return_code={rc}): {data.get('return_msg')}"
            )
        return data

    # --- 조회 ---
    def get_quote(self, symbol: str) -> Quote:
        data = self._api(self.PATH_QUOTE, self.TR_QUOTE, {"stk_cd": symbol})
        price = _parse_price(data.get("cur_prc"))
        quote = Quote(symbol=symbol, price=price, timestamp=datetime.now())
        self._last_quotes[symbol] = quote
        return quote

    def get_account(self) -> Account:
        data = self._api(
            self.PATH_ACCOUNT, self.TR_ACCOUNT,
            {"qry_tp": "0", "dmst_stex_tp": self._exchange},
        )
        # 예수금/주문가능현금 (필드명은 모의응답으로 확인 후 조정)
        cash = _parse_price(
            data.get("entr") or data.get("prsm_dpst_aset_amt") or data.get("ord_alow_amt")
        )
        positions: dict[str, Position] = {}
        for item in data.get("stk_acnt_evlt_prst", []) or data.get("acnt_evlt_remn_indv_tot", []):
            code = (item.get("stk_cd") or "").strip().lstrip("A")
            qty = int(_parse_price(item.get("rmnd_qty") or item.get("hldg_qty") or 0))
            if not code or qty <= 0:
                continue
            avg = _parse_price(item.get("pur_pric") or item.get("avg_prc") or 0)
            positions[code] = Position(symbol=code, quantity=qty, avg_price=avg)
        return Account(cash=cash, positions=positions)

    def get_position(self, symbol: str) -> Position | None:
        return self.get_account().positions.get(symbol)

    # --- 주문 ---
    def place_order(self, order: Order) -> Order:
        api_id = self.TR_BUY if order.side == Side.BUY else self.TR_SELL
        is_market = order.order_type == OrderType.MARKET
        body = {
            "dmst_stex_tp": self._exchange,
            "stk_cd": order.symbol,
            "ord_qty": str(order.quantity),
            "ord_uv": "" if is_market else str(int(order.limit_price or 0)),
            "trde_tp": "3" if is_market else "0",  # 3:시장가, 0:보통(지정가)
        }
        data = self._api(self.PATH_ORDER, api_id, body)
        order.order_id = data.get("ord_no")
        # 접수 성공(return_code 0). 실제 체결여부는 별도 체결조회 필요.
        order.status = OrderStatus.PENDING
        return order

    def cancel_order(self, order_id: str) -> bool:
        # 취소주문 TR(kt10003 등)은 원주문번호/수량이 필요.
        raise NotImplementedError(
            "취소주문은 원주문번호·수량이 필요합니다. 모의투자 응답 확인 후 구현하세요."
        )

    # --- 스케줄러 호환(선택) ---
    def last_prices(self) -> dict[str, float]:
        return {s: q.price for s, q in self._last_quotes.items()}

    def equity(self) -> float:
        acct = self.get_account()
        total = acct.cash
        for sym, pos in acct.positions.items():
            q = self._last_quotes.get(sym)
            total += pos.quantity * (q.price if q else pos.avg_price)
        return total
