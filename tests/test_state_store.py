from datetime import datetime, timedelta

from src.state_store import AlertStateStore, make_alert_key


def test_make_alert_key():
    assert make_alert_key("ETHUSDT", "15m", "macd_rebound") == "ETHUSDT_15m_macd_rebound"


def test_cooldown_blocks_then_allows_after_window(tmp_path):
    path = tmp_path / "alert_state.json"
    store = AlertStateStore(path)
    key = make_alert_key("ETHUSDT", "15m", "macd_rebound")
    now = datetime(2026, 6, 9, 20, 7, 0)

    allowed, _ = store.can_alert(key, cooldown_minutes=30, now=now)
    assert allowed

    store.record_alert(key, 1681.78, now=now)

    allowed, reason = store.can_alert(key, cooldown_minutes=30, now=now + timedelta(minutes=29))
    assert not allowed
    assert "cooldown active" in reason

    allowed, _ = store.can_alert(key, cooldown_minutes=30, now=now + timedelta(minutes=31))
    assert allowed

    reloaded = AlertStateStore(path)
    assert reloaded.state[key]["last_price"] == 1681.78
