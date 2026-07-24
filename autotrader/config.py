"""YAML 설정 로더.

config.yaml 예시는 config.example.yaml 참고.
표준 라이브러리만으로 동작하도록 간단한 파서를 포함하되,
PyYAML이 설치돼 있으면 우선 사용한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from autotrader.strategy.rule_engine import SymbolRule


def kiwoom_credentials_from_env() -> tuple[str, str, str]:
    """환경변수에서 키움 인증정보를 읽는다.

    필요: KIWOOM_APP_KEY, KIWOOM_APP_SECRET, KIWOOM_ACCOUNT_NO
    (키는 절대 코드/저장소에 넣지 말고 환경변수나 .env로 주입)
    """
    app_key = os.environ.get("KIWOOM_APP_KEY", "")
    app_secret = os.environ.get("KIWOOM_APP_SECRET", "")
    account_no = os.environ.get("KIWOOM_ACCOUNT_NO", "")
    missing = [
        name for name, val in [
            ("KIWOOM_APP_KEY", app_key),
            ("KIWOOM_APP_SECRET", app_secret),
            ("KIWOOM_ACCOUNT_NO", account_no),
        ] if not val
    ]
    if missing:
        raise RuntimeError(
            "키움 인증정보 환경변수가 없습니다: " + ", ".join(missing) +
            "\n예) export KIWOOM_APP_KEY=... KIWOOM_APP_SECRET=... KIWOOM_ACCOUNT_NO=..."
        )
    return app_key, app_secret, account_no


def _load_yaml(path: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - 안내용
        raise RuntimeError(
            "PyYAML이 필요합니다. `pip install -r requirements.txt` 후 다시 실행하세요."
        ) from exc
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class AppConfig:
    broker: str
    cash: float
    order_type: str
    steps: int
    rules: list[SymbolRule]
    credentials: dict[str, Any]


def load_config(path: str) -> AppConfig:
    data = _load_yaml(path)

    rules: list[SymbolRule] = []
    for item in data.get("rules", []):
        rules.append(SymbolRule(**item))

    return AppConfig(
        broker=data.get("broker", "paper"),
        cash=float(data.get("cash", 10_000_000)),
        order_type=data.get("order_type", "MARKET"),
        steps=int(data.get("steps", 100)),
        rules=rules,
        credentials=data.get("credentials", {}),
    )
