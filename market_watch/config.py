from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Target:
    id: str
    name: str
    group: str
    preferred_source: str
    yahoo_symbol: str | None = None
    stooq_symbol: str | None = None
    finmind_dataset: str | None = None


@dataclass(frozen=True)
class AppConfig:
    lookback_days: int
    output_dir: Path
    targets: list[Target]


def load_config(path: str | Path = "config/targets.yaml") -> AppConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    targets = [Target(**item) for item in data["targets"]]
    return AppConfig(
        lookback_days=int(data.get("lookback_days", 260)),
        output_dir=Path(data.get("output_dir", "reports")),
        targets=targets,
    )


def target_to_dict(target: Target) -> dict[str, Any]:
    return {
        "id": target.id,
        "name": target.name,
        "group": target.group,
        "preferred_source": target.preferred_source,
        "yahoo_symbol": target.yahoo_symbol,
        "stooq_symbol": target.stooq_symbol,
        "finmind_dataset": target.finmind_dataset,
    }
