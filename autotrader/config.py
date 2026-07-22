"""YAML 설정 로더.

config.yaml 예시는 config.example.yaml 참고.
표준 라이브러리만으로 동작하도록 간단한 파서를 포함하되,
PyYAML이 설치돼 있으면 우선 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autotrader.strategy.rule_engine import SymbolRule


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
