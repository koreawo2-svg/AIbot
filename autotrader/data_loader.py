"""CSV 과거 주가 로더.

네이버/KRX/야후파이낸스 등에서 받은 일봉 CSV를 읽어 종가 시계열로 변환한다.
컬럼명(날짜/종가)을 자동 인식하고, "72,000" 같은 천단위 콤마도 처리한다.

지원 예시 컬럼:
  날짜: Date, date, 날짜, 일자, Datetime
  종가: Close, close, 종가, Adj Close, adjclose
"""
from __future__ import annotations

import csv

_DATE_CANDIDATES = ("date", "날짜", "일자", "datetime", "time", "기준일자")
_CLOSE_CANDIDATES = ("close", "종가", "adj close", "adjclose", "adj_close", "현재가")


def _clean_number(raw: str) -> float:
    """'72,000', '"72000"', ' 72000 ' 등을 float으로 정제."""
    s = raw.strip().strip('"').strip().replace(",", "")
    if s == "":
        raise ValueError("빈 값")
    return float(s)


def _match_column(fieldnames: list[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {f.strip().lower(): f for f in fieldnames}
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    # 부분 일치도 시도
    for key, original in lowered.items():
        if any(cand in key for cand in candidates):
            return original
    return None


def load_close_series(
    path: str,
    date_col: str | None = None,
    price_col: str | None = None,
) -> tuple[list[str], list[float]]:
    """CSV에서 (날짜 리스트, 종가 리스트)를 날짜 오름차순으로 반환.

    date_col/price_col을 직접 지정하지 않으면 컬럼명을 자동 인식한다.
    """
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV 헤더를 읽을 수 없습니다: {path}")

        dcol = date_col or _match_column(reader.fieldnames, _DATE_CANDIDATES)
        pcol = price_col or _match_column(reader.fieldnames, _CLOSE_CANDIDATES)
        if pcol is None:
            raise ValueError(
                f"종가 컬럼을 찾지 못했습니다. 컬럼: {reader.fieldnames}. "
                "price_col 인자로 직접 지정하세요."
            )

        rows: list[tuple[str, float]] = []
        for line in reader:
            raw_price = line.get(pcol, "")
            if raw_price is None or str(raw_price).strip() == "":
                continue
            try:
                price = _clean_number(str(raw_price))
            except ValueError:
                continue  # 숫자로 못 바꾸는 행은 건너뜀
            date = str(line.get(dcol, "")).strip() if dcol else ""
            rows.append((date, price))

    if not rows:
        raise ValueError(f"유효한 가격 데이터가 없습니다: {path}")

    # 날짜가 있으면 날짜 오름차순 정렬(ISO 문자열은 사전식=시간순)
    if any(d for d, _ in rows):
        rows.sort(key=lambda r: r[0])

    dates = [d for d, _ in rows]
    prices = [p for _, p in rows]
    return dates, prices
