from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def append_jsonl(path: str | Path, payload: dict[str, Any]) -> None:
    jsonl_path = Path(path)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")
