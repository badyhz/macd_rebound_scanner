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
            "intervals": ["5m"],
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


def test_scan_once_all_symbols_mode_uses_exchange_markets(tmp_path, monkeypatch):
    cfg = {
        "_base_dir": str(tmp_path),
        "scan": {
            "intervals": ["5m"],
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
    monkeypatch.setattr(scheduler, "send_feishu_text", lambda *args, **kwargs: {"_http_status": 200, "code": 0})

    result = scheduler.send_force_alert(cfg, "BTCUSDT", dry_run=False)

    assert result["sent"] is True
    assert result["webhook_http_status"] == 200
