from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "exchange": {"name": "binance", "market": "futures"},
    "scan": {
        "all_usdt_perpetual": True,
        "intervals": ["15m", "1h"],
        "symbols": ["ETHUSDT", "BTCUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "XRPUSDT"],
        "ohlcv_limit": 150,
        "loop_seconds": 120,
        "use_closed_candle_only": True,
        "exclude_symbols": [],
        "exclude_non_ascii_symbols": True,
        "max_symbols": None,
    },
    "strategy": {
        "name": "macd_rebound",
        "lookback_drop_bars": 48,
        "min_drop_pct": 1.5,
        "low_check_bars": 12,
        "low_break_tolerance_pct": 0.2,
        "macd": {"fast": 12, "slow": 26, "signal": 9, "shrink_bars": 3},
        "ma": {
            "short": 7,
            "mid": 25,
            "long": 99,
            "require_above_ma7": True,
            "require_above_ma25": True,
            "require_above_ma99": False,
        },
        "volume": {"ma_bars": 5, "multiplier": 1.3},
    },
    "alert": {
        "provider": "feishu",
        "cooldown_minutes": 30,
        "min_send_interval_seconds": 1.2,
        "webhook_url_env": "FEISHU_WEBHOOK_URL",
        "secret_env": "FEISHU_SECRET",
    },
    "heartbeat": {
        "enabled": True,
        "send_on_start": True,
        "interval_rounds": 120,
    },
    "paths": {
        "state_file": "data/alert_state.json",
        "signals_csv": "data/signals.csv",
        "log_file": "logs/macd_rebound_scanner.log",
        "scan_detail_jsonl": "logs/scan_detail.jsonl",
        "alerts_jsonl": "logs/alerts.jsonl",
        "errors_log": "logs/errors.log",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")

    cfg = _deep_merge(DEFAULT_CONFIG, raw)
    cfg["_base_dir"] = str(path.parent)
    return cfg


def resolve_path(cfg: dict[str, Any], value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return Path(cfg.get("_base_dir", ".")).resolve() / path
