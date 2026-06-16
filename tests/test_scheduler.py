import json
from datetime import datetime

from src import scheduler


class FakeExchange:
    def load_markets(self):
        return {
            "BTC/USDT:USDT": {
                "symbol": "BTC/USDT:USDT",
                "quote": "USDT",
                "swap": True,
                "linear": True,
                "info": {"status": "TRADING", "contractType": "PERPETUAL", "quoteAsset": "USDT"},
            },
            "ETH/USDT:USDT": {
                "symbol": "ETH/USDT:USDT",
                "quote": "USDT",
                "swap": True,
                "linear": True,
                "info": {"status": "TRADING", "contractType": "PERPETUAL", "quoteAsset": "USDT"},
            },
            "龙虾/USDT:USDT": {
                "symbol": "龙虾/USDT:USDT",
                "quote": "USDT",
                "swap": True,
                "linear": True,
                "info": {"status": "TRADING", "contractType": "PERPETUAL", "quoteAsset": "USDT"},
            },
        }

    def fetch_ohlcv(self, symbol, timeframe, limit):
        return [[1700000000000 + index * 300000, 1, 2, 0.5, 1.5, 100] for index in range(limit)]


def test_dry_run_does_not_call_feishu(tmp_path, monkeypatch):
    cfg = {
        "_base_dir": str(tmp_path),
        "scan": {
            "intervals": ["15m"],
            "symbols": ["ETHUSDT"],
            "all_usdt_perpetual": False,
            "ohlcv_limit": 150,
            "use_closed_candle_only": True,
        },
        "strategy": {"name": "macd_rebound"},
        "alert": {
            "cooldown_minutes": 30,
            "webhook_url_env": "FEISHU_WEBHOOK_URL",
            "secret_env": "FEISHU_SECRET",
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

    evaluation = {
        "triggered": True,
        "level": "B",
        "reason": ["测试触发"],
        "failed_conditions": [],
        "metrics": {
            "price": 1.5,
            "drop_pct": 2.0,
            "dif": 0.1,
            "dea": 0.0,
            "hist": 0.1,
            "ma7": 1.2,
            "ma25": 1.1,
            "ma99": 2.0,
            "volume": 100.0,
            "volume_ma5": 50.0,
            "volume_ratio": 2.0,
            "above_ma99": False,
        },
    }

    def fake_evaluate(df, strategy_cfg):
        return evaluation

    def fail_send(*args, **kwargs):
        raise AssertionError("dry-run must not call Feishu")

    monkeypatch.setattr(scheduler, "evaluate_macd_rebound", fake_evaluate)
    monkeypatch.setattr(scheduler, "send_feishu_text", fail_send)

    stats = scheduler.scan_once(cfg, dry_run=True, exchange=FakeExchange())

    assert stats["triggered"] == 1
    assert stats["alerted"] == 1
    assert (tmp_path / "data" / "signals.csv").exists()
    assert (tmp_path / "logs" / "alerts.jsonl").exists()
    assert not (tmp_path / "data" / "alert_state.json").exists()


def test_feishu_business_failure_does_not_record_alert_state(tmp_path, monkeypatch):
    cfg = {
        "_base_dir": str(tmp_path),
        "scan": {
            "intervals": ["15m"],
            "symbols": ["ETHUSDT"],
            "all_usdt_perpetual": False,
            "ohlcv_limit": 150,
            "use_closed_candle_only": True,
        },
        "strategy": {"name": "macd_rebound"},
        "alert": {
            "cooldown_minutes": 30,
            "min_send_interval_seconds": 0,
            "webhook_url_env": "FEISHU_WEBHOOK_URL",
            "secret_env": "FEISHU_SECRET",
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

    evaluation = {
        "triggered": True,
        "level": "B",
        "reason": ["测试触发"],
        "failed_conditions": [],
        "metrics": {
            "price": 1.5,
            "dif": 0.1,
            "dea": 0.0,
            "hist": 0.1,
            "ma7": 1.2,
            "ma25": 1.1,
            "ma99": 2.0,
            "volume": 100.0,
            "volume_ma5": 50.0,
            "volume_ratio": 2.0,
            "above_ma99": False,
        },
    }

    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.test/webhook")
    monkeypatch.setattr(scheduler, "evaluate_macd_rebound", lambda df, strategy_cfg: evaluation)
    monkeypatch.setattr(
        scheduler,
        "send_feishu_text",
        lambda *args, **kwargs: {"_http_status": 200, "code": 11232, "msg": "frequency limited"},
    )

    stats = scheduler.scan_once(cfg, dry_run=False, exchange=FakeExchange())

    assert stats["triggered"] == 1
    assert stats["alerted"] == 0
    assert stats["errors"] == 0
    assert not (tmp_path / "data" / "alert_state.json").exists()
    record = json.loads((tmp_path / "logs" / "alerts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["sent"] is False
    assert record["webhook_http_status"] == 200
    assert record["response"]["code"] == 11232
    assert record["error_message"] == "Feishu response code=11232 msg=frequency limited"


def test_scan_once_all_symbols_mode_uses_exchange_markets(tmp_path, monkeypatch):
    cfg = {
        "_base_dir": str(tmp_path),
        "scan": {
            "intervals": ["15m"],
            "symbols": ["IGNORED"],
            "all_usdt_perpetual": True,
            "exclude_symbols": ["ETHUSDT"],
            "exclude_non_ascii_symbols": True,
            "ohlcv_limit": 150,
            "use_closed_candle_only": True,
        },
        "strategy": {"name": "macd_rebound"},
        "alert": {
            "cooldown_minutes": 30,
            "webhook_url_env": "FEISHU_WEBHOOK_URL",
            "secret_env": "FEISHU_SECRET",
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

    def fake_evaluate(df, strategy_cfg):
        return {"triggered": False, "level": None, "reason": [], "failed_conditions": ["no"], "metrics": {}}

    monkeypatch.setattr(scheduler, "evaluate_macd_rebound", fake_evaluate)

    stats = scheduler.scan_once(cfg, dry_run=True, exchange=FakeExchange())

    assert stats["scanned"] == 1
    assert stats["errors"] == 0
    detail = (tmp_path / "logs" / "scan_detail.jsonl").read_text(encoding="utf-8")
    assert '"symbol": "BTCUSDT"' in detail
    assert "ETHUSDT" not in detail
    assert "龙虾USDT" not in detail


def test_send_force_alert_dry_run_does_not_call_feishu(tmp_path, monkeypatch):
    cfg = {
        "_base_dir": str(tmp_path),
        "alert": {"webhook_url_env": "FEISHU_WEBHOOK_URL", "secret_env": "FEISHU_SECRET"},
        "paths": {"alerts_jsonl": "logs/alerts.jsonl"},
    }

    def fail_send(*args, **kwargs):
        raise AssertionError("dry-run must not call Feishu")

    monkeypatch.setattr(scheduler, "send_feishu_text", fail_send)
    result = scheduler.send_force_alert(cfg, "BTCUSDT", dry_run=True)

    assert result["sent"] is False
    assert result["dry_run"] is True
    assert (tmp_path / "logs" / "alerts.jsonl").exists()


def test_send_force_alert_records_success(tmp_path, monkeypatch):
    cfg = {
        "_base_dir": str(tmp_path),
        "alert": {"webhook_url_env": "FEISHU_WEBHOOK_URL", "secret_env": "FEISHU_SECRET"},
        "paths": {"alerts_jsonl": "logs/alerts.jsonl"},
    }

    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.test/webhook")
    sent_messages = []

    def fake_send(webhook_url, content, secret=None):
        sent_messages.append(content)
        return {"_http_status": 200, "code": 0}

    monkeypatch.setattr(scheduler, "send_feishu_text", fake_send)

    result = scheduler.send_force_alert(cfg, "BTCUSDT", dry_run=False)

    assert result["sent"] is True
    assert result["webhook_http_status"] == 200
    assert "round_id:" in sent_messages[0]
    assert "周期：15m" in sent_messages[0]
    assert "信号来源: force_alert" in sent_messages[0]
    assert "是否冷却跳过: 否" in sent_messages[0]


def test_send_force_alert_records_business_failure(tmp_path, monkeypatch):
    cfg = {
        "_base_dir": str(tmp_path),
        "alert": {"webhook_url_env": "FEISHU_WEBHOOK_URL", "secret_env": "FEISHU_SECRET"},
        "paths": {"alerts_jsonl": "logs/alerts.jsonl"},
    }

    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.test/webhook")
    monkeypatch.setattr(
        scheduler,
        "send_feishu_text",
        lambda *args, **kwargs: {"_http_status": 200, "code": 11232, "msg": "frequency limited"},
    )

    result = scheduler.send_force_alert(cfg, "BTCUSDT", dry_run=False)

    assert result["sent"] is False
    assert result["webhook_http_status"] == 200
    assert result["error_message"] == "Feishu response code=11232 msg=frequency limited"


def test_run_loop_sends_start_and_runtime_heartbeat(monkeypatch, tmp_path):
    cfg = {
        "_base_dir": str(tmp_path),
        "scan": {"loop_seconds": 120, "intervals": ["15m"]},
        "alert": {"webhook_url_env": "FEISHU_WEBHOOK_URL", "secret_env": "FEISHU_SECRET"},
        "heartbeat": {"enabled": True, "send_on_start": True, "interval_rounds": 1},
        "paths": {"alerts_jsonl": "logs/alerts.jsonl", "errors_log": "logs/errors.log"},
    }
    calls = []
    summary = {
        "round_id": "r1",
        "market": "binance_um_futures",
        "timeframe": "15m",
        "symbols_total": 1,
        "symbols_scanned": 1,
        "triggered": 0,
        "alerted": 0,
        "cooldown_skipped": 0,
        "errors": 0,
        "duration_seconds": 1.0,
    }

    monkeypatch.setattr(scheduler, "create_exchange", lambda: FakeExchange())
    monkeypatch.setattr(scheduler, "scan_once", lambda *args, **kwargs: ({"scanned": 1, "errors": 0}, summary))
    monkeypatch.setattr(scheduler, "send_start_heartbeat", lambda *args, **kwargs: calls.append("start"))
    monkeypatch.setattr(scheduler, "send_runtime_heartbeat", lambda *args, **kwargs: calls.append("runtime"))

    scheduler.run_loop(cfg, once=True)

    assert calls == ["start", "runtime"]
