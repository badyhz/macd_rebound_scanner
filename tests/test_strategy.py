from datetime import datetime, timedelta

import pandas as pd

from src.strategy import (
    evaluate_macd_rebound,
    macd_hist_crossed_up,
    macd_negative_hist_shrinking,
    price_above_required_mas,
    volume_expanded,
)


def _strategy_cfg():
    return {
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
    }


def _signal_df():
    rows = []
    start = datetime(2026, 6, 9, 10, 0, 0)
    for index in range(110):
        close = 100.0
        rows.append(
            {
                "timestamp": int((start + timedelta(minutes=5 * index)).timestamp() * 1000),
                "datetime": start + timedelta(minutes=5 * index),
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": close,
                "volume": 100.0,
                "ma7": 99.0,
                "ma25": 98.8,
                "ma99": 101.0,
                "vol_ma5": 100.0,
                "dif": -0.2,
                "dea": -0.1,
                "hist": -0.6,
            }
        )

    df = pd.DataFrame(rows)
    df.loc[df.index[-48], "high"] = 102.0
    df.loc[df.index[-20], "low"] = 98.0
    df.loc[df.index[-12:], "low"] = 98.0
    df.loc[df.index[-4], "hist"] = -0.5
    df.loc[df.index[-3], "hist"] = -0.4
    df.loc[df.index[-2], "hist"] = -0.3
    df.loc[df.index[-2], ["close", "dif", "dea"]] = [99.5, -0.2, -0.1]
    df.loc[df.index[-1], ["open", "high", "low", "close"]] = [99.7, 101.0, 99.0, 100.5]
    df.loc[df.index[-1], ["volume", "vol_ma5"]] = [200.0, 100.0]
    df.loc[df.index[-1], ["ma7", "ma25", "ma99"]] = [100.0, 99.8, 101.0]
    df.loc[df.index[-1], ["dif", "dea", "hist"]] = [0.1, 0.0, 0.2]
    return df


def test_macd_negative_hist_shrinking():
    assert macd_negative_hist_shrinking([-5, -4, -3])
    assert macd_negative_hist_shrinking([-5, -4, -3, -2])
    assert not macd_negative_hist_shrinking([-2, -4, -3])
    assert not macd_negative_hist_shrinking([1, 2, 3])


def test_macd_hist_crossed_up():
    assert macd_hist_crossed_up(-0.5, 0.2)
    assert not macd_hist_crossed_up(0.1, 0.3)


def test_price_above_required_mas():
    row = pd.Series({"close": 101.0, "ma7": 100.0, "ma25": 99.0, "ma99": 102.0})
    ok, failed = price_above_required_mas(row, {"require_above_ma7": True, "require_above_ma25": True})
    assert ok
    assert failed == []

    row["close"] = 98.0
    ok, failed = price_above_required_mas(row, {"require_above_ma7": True, "require_above_ma25": True})
    assert not ok
    assert "当前收盘价未站上 MA7" in failed
    assert "当前收盘价未站上 MA25" in failed


def test_volume_expanded():
    assert volume_expanded(131.0, 100.0, 1.3)
    assert not volume_expanded(130.0, 100.0, 1.3)
    assert not volume_expanded(129.0, 100.0, 1.3)


def test_evaluate_macd_rebound_triggers_b_signal():
    result = evaluate_macd_rebound(_signal_df(), _strategy_cfg())

    assert result["triggered"] is True
    assert result["level"] == "B"
    assert result["failed_conditions"] == []
    assert result["metrics"]["drop_pct"] >= 1.5
    assert result["metrics"]["dif_cross_up"] is True


def test_evaluate_macd_rebound_fails_ma_breakthrough():
    df = _signal_df()
    df.loc[df.index[-1], "close"] = 99.0
    result = evaluate_macd_rebound(df, _strategy_cfg())

    assert result["triggered"] is False
    assert "当前收盘价未站上 MA7" in result["failed_conditions"]
