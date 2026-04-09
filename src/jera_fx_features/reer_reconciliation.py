from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class PrototypeReconciliation:
    prototype_current_value: float
    source_native_latest_value: float
    source_canonical_latest_value: float
    source_latest_reference_month_end: str
    status: str
    note: str


def load_prototype_data(path: Path | str) -> dict:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    match = re.search(r"const DATA = (\{.*?\});\s*const", text, re.S)
    if not match:
        raise ValueError(f"Could not locate DATA payload in {path}")
    return json.loads(match.group(1))


def reconcile_prototype_reer(
    prototype_path: Path | str,
    latest_native_value: float,
    latest_canonical_value: float,
    latest_reference_month_end: str,
) -> PrototypeReconciliation:
    data = load_prototype_data(prototype_path)
    prototype_current = float(data["core"]["current"]["reer"])
    return PrototypeReconciliation(
        prototype_current_value=prototype_current,
        source_native_latest_value=float(latest_native_value),
        source_canonical_latest_value=float(latest_canonical_value),
        source_latest_reference_month_end=latest_reference_month_end,
        status="legacy_reference_only",
        note=(
            "Prototype REER values are legacy reference visuals only. "
            "They do not match the source-native workbook scale exactly and must not be treated as source data."
        ),
    )

