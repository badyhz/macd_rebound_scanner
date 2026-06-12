from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any


FIELDNAMES = [
    "time",
    "symbol",
    "interval",
    "price",
    "signal_level",
    "drop_pct",
    "dif",
    "dea",
    "hist",
    "ma7",
    "ma25",
    "ma99",
    "volume",
    "volume_ma5",
    "volume_ratio",
    "above_ma99",
    "reason",
]


def append_signal(
    path: str | Path,
    symbol: str,
    interval: str,
    candle_time: datetime | str,
    evaluation: dict[str, Any],
) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    metrics = evaluation.get("metrics", {})
    row = {
        "time": candle_time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(candle_time, "strftime") else str(candle_time),
        "symbol": symbol,
        "interval": interval,
        "price": metrics.get("price"),
        "signal_level": evaluation.get("level"),
        "drop_pct": metrics.get("drop_pct"),
        "dif": metrics.get("dif"),
        "dea": metrics.get("dea"),
        "hist": metrics.get("hist"),
        "ma7": metrics.get("ma7"),
        "ma25": metrics.get("ma25"),
        "ma99": metrics.get("ma99"),
        "volume": metrics.get("volume"),
        "volume_ma5": metrics.get("volume_ma5"),
        "volume_ratio": metrics.get("volume_ratio"),
        "above_ma99": metrics.get("above_ma99"),
        "reason": " | ".join(evaluation.get("reason", [])),
    }
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
