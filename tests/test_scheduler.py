from datetime import datetime

from src import scheduler


class FakeExchange:
    def fetch_ohlcv(self, symbol, timeframe, limit):
        return [[1700000000000 + index * 300000, 1, 2, 0.5, 1.5, 100] for index in range(limit)]


def test_dry_run_does_not_call_feishu(tmp_path, monkeypatch):
    cfg = {
        "_base_dir": str(tmp_path),
        "scan": {
            "intervals": ["5m"],
            "symbols": ["ETHUSDT"],
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
    assert not (tmp_path / "data" / "alert_state.json").exists()
