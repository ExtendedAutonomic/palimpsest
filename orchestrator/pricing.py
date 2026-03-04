"""
Model pricing for Palimpsest.

Loads pricing from config/costs.yaml at import time.
To update pricing, edit config/costs.yaml only.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "costs.yaml"


def _load_pricing() -> dict[str, dict[str, float]]:
    """Load per-model pricing from costs.yaml."""
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("pricing", {})


MODEL_PRICING: dict[str, dict[str, float]] = _load_pricing()


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a given model and token counts."""
    pricing = MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
    input_cost = (input_tokens / 1_000_000) * pricing.get("input", 0.0)
    output_cost = (output_tokens / 1_000_000) * pricing.get("output", 0.0)
    return round(input_cost + output_cost, 2)
