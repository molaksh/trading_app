"""
Crypto config loader for Kraken scopes.

Parses the lightweight key/value config files in config/crypto/*.yaml.
These files are intentionally simple and use KEY = value lines.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict

from config.scope import Scope


def _parse_value(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""

    lower = value.lower()
    if lower in {"true", "false"}:
        return lower == "true"

    # Try numeric
    try:
        if "." in value:
            return float(value)
        return int(value)
    except Exception:
        pass

    # Try literal eval for lists/dicts/strings
    if value.startswith("[") or value.startswith("{") or value.startswith("(") or value.startswith("'") or value.startswith('"'):
        try:
            return ast.literal_eval(value)
        except Exception:
            return value.strip("\"'")

    return value.strip("\"'")


def _parse_kv_file(path: Path) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, raw_val = stripped.split("=", 1)
        key = key.strip()
        raw_val = raw_val.strip()
        if not key:
            continue
        data[key] = _parse_value(raw_val)
    return data


def load_crypto_config(scope: Scope) -> Dict[str, Any]:
    """
    Load crypto config for the given scope.

    Args:
        scope: Scope instance

    Returns:
        Dict of config values

    Raises:
        FileNotFoundError if config file missing
    """
    env = scope.env.lower()
    broker = scope.broker.lower()
    mode = scope.mode.lower()
    market = scope.market.lower()

    if broker != "kraken" or mode != "crypto":
        raise ValueError(f"Crypto config requested for non-crypto scope: {scope}")

    filename = f"{env}.{broker}.{mode}.{market}.yaml"
    config_path = Path(__file__).resolve().parent / filename
    if not config_path.exists():
        raise FileNotFoundError(f"Missing crypto config: {config_path}")

    return _parse_kv_file(config_path)
