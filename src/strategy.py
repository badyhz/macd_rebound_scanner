from __future__ import annotations

from typing import Any

import pandas as pd


def macd_negative_hist_shrinking(values: list[float] | pd.Series) -> bool:
    series = list(values)
    if len(series) < 3:
        return False
    window = series[-3:]
    return all(value < 0 for value in window) and window[1] > window[0] and window[2] > window[1]


def macd_hist_crossed_up(previous_hist: float, current_hist: float) -> bool:
    return previous_hist <= 0 and current_hist > 0


def dif_crossed_up(previous_dif: float, previous_dea: float, current_dif: float, current_dea: float) -> bool:
    return previous_dif <= previous_dea and current_dif > current_dea


def price_above_required_mas(row: pd.Series, ma_cfg: dict[str, Any]) -> tuple[bool, list[str]]:
    failed: list[str] = []
    close = float(row["close"])
    if ma_cfg.get("require_above_ma7", True) and not close > float(row["ma7"]):
        failed.append("当前收盘价未站上 MA7")
    if ma_cfg.get("require_above_ma25", True) and not close > float(row["ma25"]):
        failed.append("当前收盘价未站上 MA25")
    if ma_cfg.get("require_above_ma99", False) and not close > float(row["ma99"]):
        failed.append("当前收盘价未站上 MA99")
    return len(failed) == 0, failed


def volume_expanded(current_volume: float, volume_ma: float, multiplier: float) -> bool:
    return current_volume > volume_ma * multiplier


def evaluate_macd_rebound(df: pd.DataFrame, cfg: dict) -> dict:
    """
    Evaluate B-level short-term MACD rebound signal using closed candles only.
    """
    result = {
        "triggered": False,
        "level": None,
        "reason": [],
        "metrics": {},
        "failed_conditions": [],
    }
    required_columns = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "ma7",
        "ma25",
        "ma99",
        "vol_ma5",
        "dif",
        "dea",
        "hist",
    }
    missing = sorted(required_columns - set(df.columns))
    if missing:
        result["failed_conditions"].append(f"缺少指标字段: {', '.join(missing)}")
        return result

    lookback_drop_bars = int(cfg.get("lookback_drop_bars", 48))
    low_check_bars = int(cfg.get("low_check_bars", 12))
    min_required_rows = max(lookback_drop_bars, low_check_bars, 99) + 4
    if len(df) < min_required_rows:
        result["failed_conditions"].append(f"K线数量不足: {len(df)} < {min_required_rows}")
        return result

    working = df.tail(max(lookback_drop_bars, low_check_bars, 99) + 4).copy()
    if working[list(required_columns)].tail(1).isna().any(axis=None):
        result["failed_conditions"].append("最新K线存在未完成指标")
        return result

    latest = working.iloc[-1]
    previous = working.iloc[-2]
    drop_window = working.tail(lookback_drop_bars)
    low_window = working.tail(low_check_bars)

    recent_high = float(drop_window["high"].max())
    recent_low = float(drop_window["low"].min())
    drop_pct = (recent_high - recent_low) / recent_high * 100 if recent_high else 0.0

    recent_12_low = float(low_window["low"].min())
    tolerance_pct = float(cfg.get("low_break_tolerance_pct", 0.2))
    current_close = float(latest["close"])
    current_low = float(latest["low"])
    current_open = float(latest["open"])
    previous_close = float(previous["close"])

    hist_values = [float(working["hist"].iloc[-4]), float(working["hist"].iloc[-3]), float(working["hist"].iloc[-2])]
    hist_shrinking = macd_negative_hist_shrinking(hist_values)
    hist_cross_up = macd_hist_crossed_up(float(previous["hist"]), float(latest["hist"]))
    dif_cross_up = dif_crossed_up(
        float(previous["dif"]),
        float(previous["dea"]),
        float(latest["dif"]),
        float(latest["dea"]),
    )
    ma_ok, ma_failed = price_above_required_mas(latest, cfg.get("ma", {}))
    volume_ratio = float(latest["volume"]) / float(latest["vol_ma5"]) if float(latest["vol_ma5"]) else 0.0
    vol_ok = volume_expanded(
        float(latest["volume"]),
        float(latest["vol_ma5"]),
        float(cfg.get("volume", {}).get("multiplier", 1.3)),
    )
    above_ma99 = current_close > float(latest["ma99"])

    metrics = {
        "recent_high": recent_high,
        "recent_low": recent_low,
        "drop_pct": drop_pct,
        "recent_12_low": recent_12_low,
        "dif": float(latest["dif"]),
        "dea": float(latest["dea"]),
        "hist": float(latest["hist"]),
        "previous_hist": float(previous["hist"]),
        "dif_cross_up": dif_cross_up,
        "ma7": float(latest["ma7"]),
        "ma25": float(latest["ma25"]),
        "ma99": float(latest["ma99"]),
        "volume": float(latest["volume"]),
        "volume_ma5": float(latest["vol_ma5"]),
        "volume_ratio": volume_ratio,
        "above_ma99": above_ma99,
        "price": current_close,
    }
    result["metrics"] = metrics

    if drop_pct >= float(cfg.get("min_drop_pct", 1.5)):
        result["reason"].append(f"最近{lookback_drop_bars}根K线跌幅 {drop_pct:.2f}%，满足明显下跌")
    else:
        result["failed_conditions"].append(
            f"最近{lookback_drop_bars}根K线跌幅不足: {drop_pct:.2f}%"
        )

    close_left_low = current_close > recent_12_low * (1 + tolerance_pct / 100)
    low_not_broken = current_low >= recent_12_low * (1 - tolerance_pct / 100)
    if close_left_low and low_not_broken:
        result["reason"].append("当前价格离开近期低点，且未明显跌破最近低点")
    else:
        result["failed_conditions"].append("当前价格仍贴近低点或明显跌破最近低点")

    if hist_shrinking:
        result["reason"].append("最近3根 MACD 负柱连续缩小，空头动能衰竭")
    else:
        result["failed_conditions"].append("MACD 负柱未连续缩小")

    if hist_cross_up:
        result["reason"].append(
            f"MACD柱由 {float(previous['hist']):.4f} 转为 {float(latest['hist']):.4f}，动能翻多"
        )
    else:
        result["failed_conditions"].append("MACD柱未由负转正")

    if current_close > current_open and current_close > previous_close:
        result["reason"].append("当前K线阳线并高于上一根收盘价")
    else:
        result["failed_conditions"].append("当前K线不是放量反弹所需的上涨K线")

    if ma_ok:
        result["reason"].append("当前收盘价站上 MA7 / MA25")
    else:
        result["failed_conditions"].extend(ma_failed)

    if vol_ok:
        result["reason"].append(f"当前成交量为 VOL_MA5 的 {volume_ratio:.2f} 倍")
    else:
        result["failed_conditions"].append(f"当前成交量未超过 VOL_MA5 的 {float(cfg.get('volume', {}).get('multiplier', 1.3)):.2f} 倍")

    result["triggered"] = len(result["failed_conditions"]) == 0
    result["level"] = "B" if result["triggered"] else None
    return result
