import json

from src import heartbeat
from src.config import DEFAULT_CONFIG, load_config


def _cfg(tmp_path, enabled=True, send_on_start=True, interval_rounds=2):
    return {
        "_base_dir": str(tmp_path),
        "scan": {
            "all_usdt_perpetual": True,
            "intervals": ["15m", "1h"],
            "loop_seconds": 120,
        },
        "alert": {"webhook_url_env": "FEISHU_WEBHOOK_URL", "secret_env": "FEISHU_SECRET"},
        "heartbeat": {
            "enabled": enabled,
            "send_on_start": send_on_start,
            "interval_rounds": interval_rounds,
        },
        "paths": {
            "alerts_jsonl": "logs/alerts.jsonl",
            "errors_log": "logs/errors.log",
        },
    }


def test_default_config_uses_heartbeat_and_15m_1h(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")

    cfg = load_config(config_path)

    assert DEFAULT_CONFIG["scan"]["intervals"] == ["15m", "1h"]
    assert cfg["scan"]["intervals"] == ["15m", "1h"]
    assert cfg["scan"]["loop_seconds"] == 120
    assert cfg["heartbeat"]["enabled"] is True
    assert cfg["heartbeat"]["send_on_start"] is True
    assert cfg["heartbeat"]["interval_rounds"] == 120


def test_heartbeat_disabled_does_not_send(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, enabled=False)

    def fail_send(*args, **kwargs):
        raise AssertionError("disabled heartbeat must not send")

    monkeypatch.setattr(heartbeat, "send_feishu_text", fail_send)

    assert heartbeat.send_start_heartbeat(cfg, dry_run=False) is None
    assert heartbeat.send_runtime_heartbeat(cfg, {"round_id": "r1"}, dry_run=False) is None
    assert not (tmp_path / "logs" / "alerts.jsonl").exists()


def test_start_heartbeat_writes_alert_record(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    sent_messages = []

    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.test/webhook")
    monkeypatch.setattr(
        heartbeat,
        "send_feishu_text",
        lambda webhook_url, content, secret=None: sent_messages.append(content) or {"_http_status": 200, "code": 0},
    )

    result = heartbeat.send_start_heartbeat(cfg, dry_run=False)

    assert result["sent"] is True
    assert result["webhook_http_status"] == 200
    assert "【MACD扫描器已启动】" in sent_messages[0]
    assert "信号来源：heartbeat_start" in sent_messages[0]
    assert "周期：15m,1h" in sent_messages[0]
    record = json.loads((tmp_path / "logs" / "alerts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["alert_type"] == "heartbeat_start"
    assert record["signal_source"] == "heartbeat_start"


def test_runtime_heartbeat_interval_gate():
    cfg = {"heartbeat": {"enabled": True, "interval_rounds": 2}}

    assert heartbeat.should_send_runtime_heartbeat(cfg, 1) is False
    assert heartbeat.should_send_runtime_heartbeat(cfg, 2) is True
    assert heartbeat.should_send_runtime_heartbeat(cfg, 3) is False
    assert heartbeat.should_send_runtime_heartbeat(cfg, 4) is True


def test_runtime_heartbeat_writes_summary(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    summary = {
        "round_id": "20260613-020000",
        "market": "binance_um_futures",
        "timeframe": "15m",
        "symbols_total": 527,
        "symbols_scanned": 524,
        "triggered": 0,
        "alerted": 0,
        "cooldown_skipped": 0,
        "errors": 0,
        "duration_seconds": 54.08,
    }
    sent_messages = []

    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.test/webhook")
    monkeypatch.setattr(
        heartbeat,
        "send_feishu_text",
        lambda webhook_url, content, secret=None: sent_messages.append(content) or {"_http_status": 200, "code": 0},
    )

    result = heartbeat.send_runtime_heartbeat(cfg, summary, dry_run=False)

    assert result["sent"] is True
    assert "【MACD扫描器心跳】" in sent_messages[0]
    assert "信号来源：heartbeat" in sent_messages[0]
    assert "周期：15m" in sent_messages[0]
    assert "symbols_scanned：524" in sent_messages[0]
    record = json.loads((tmp_path / "logs" / "alerts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["alert_type"] == "heartbeat"
    assert record["summary"]["symbols_scanned"] == 524


def test_runtime_heartbeat_failure_does_not_raise(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)

    def fail_send(*args, **kwargs):
        raise RuntimeError("feishu down")

    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.test/webhook")
    monkeypatch.setattr(heartbeat, "send_feishu_text", fail_send)

    result = heartbeat.send_runtime_heartbeat(cfg, {"round_id": "r1", "timeframe": "15m"}, dry_run=False)

    assert result["sent"] is False
    assert "feishu down" in result["error_message"]
    assert (tmp_path / "logs" / "alerts.jsonl").exists()
    assert "RuntimeError: feishu down" in (tmp_path / "logs" / "errors.log").read_text(encoding="utf-8")
