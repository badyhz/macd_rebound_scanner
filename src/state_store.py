from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def make_alert_key(symbol: str, interval: str, strategy_name: str) -> str:
    return f"{symbol}_{interval}_{strategy_name}"


class AlertStateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.state: dict[str, Any] = {}
        self.load()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            self.state = {}
            return self.state
        try:
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self.state, dict):
                self.state = {}
        except json.JSONDecodeError:
            self.state = {}
        return self.state

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def can_alert(
        self,
        key: str,
        cooldown_minutes: int,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        now = now or datetime.now()
        entry = self.state.get(key)
        if not entry or not entry.get("last_alert_time"):
            return True, "no previous alert"

        try:
            last_alert_time = datetime.fromisoformat(entry["last_alert_time"])
        except ValueError:
            return True, "invalid previous alert time"

        elapsed = now - last_alert_time
        cooldown = timedelta(minutes=cooldown_minutes)
        if elapsed >= cooldown:
            return True, f"cooldown passed: {elapsed}"
        remaining = cooldown - elapsed
        return False, f"cooldown active, remaining {remaining}"

    def record_alert(
        self,
        key: str,
        price: float,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now()
        self.state[key] = {
            "last_alert_time": now.isoformat(timespec="seconds"),
            "last_price": float(price),
        }
        self.save()
