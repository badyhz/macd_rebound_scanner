from datetime import datetime, timezone

from src.notifier_feishu import format_signal_message


def _evaluation(price):
    return {
        "reason": ["测试触发"],
        "metrics": {
            "price": price,
            "dif": 0.000012345,
            "dea": 0.000001234,
            "hist": 0.000011111,
            "ma7": price * 0.98,
            "ma25": price * 0.95,
            "ma99": price * 1.1,
            "volume": 1234,
            "volume_ma5": 1000,
            "volume_ratio": 1.23,
            "above_ma99": False,
        },
    }


def test_format_signal_message_shows_utc_beijing_and_metadata():
    message = format_signal_message(
        "LOWUSDT",
        "15m",
        datetime(2026, 6, 12, 16, 45, 0),
        _evaluation(0.00061234),
        round_id="20260613-004500",
        signal_source="real_signal",
        cooldown_skipped=False,
    )

    assert message.startswith("【短线反弹启动信号-15 分钟】")
    assert "round_id：20260613-004500" in message
    assert "信号来源：real_signal" in message
    assert "是否冷却跳过：否" in message
    assert "K线时间(UTC)：2026-06-12 16:45:00 UTC" in message
    assert "K线时间(北京时间)：2026-06-13 00:45:00 UTC+8" in message
    assert "当前价格：0.00061234" in message
    assert "DIF：0.00001234" in message
    assert "MA7：0.00060009" in message


def test_format_signal_message_uses_six_decimals_for_sub_one_price():
    message = format_signal_message(
        "MIDUSDT",
        "15m",
        datetime(2026, 6, 12, 16, 45, 0, tzinfo=timezone.utc),
        _evaluation(0.5),
    )

    assert "当前价格：0.500000" in message
    assert "DIF：0.000012" in message
    assert "MA25：0.475000" in message


def test_format_signal_message_uses_four_decimals_for_regular_price():
    message = format_signal_message(
        "BTCUSDT",
        "15m",
        "2026-06-12T16:45:00+00:00",
        _evaluation(100.0),
        signal_source="heartbeat",
    )

    assert "信号来源：heartbeat" in message
    assert "当前价格：100.0000" in message
    assert "DIF：0.0000" in message
    assert "MA99：110.0000" in message


def test_format_signal_message_uses_hour_title_label():
    message = format_signal_message(
        "BTCUSDT",
        "1h",
        "2026-06-12T16:00:00+00:00",
        _evaluation(100.0),
    )

    assert message.startswith("【短线反弹启动信号-1 小时】")
    assert "周期：1h" in message
