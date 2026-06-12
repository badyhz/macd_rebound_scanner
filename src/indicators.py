from __future__ import annotations

import pandas as pd


def ohlcv_to_dataframe(ohlcv: list[list[float]]) -> pd.DataFrame:
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = df["timestamp"].astype("int64")
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    numeric_columns = ["open", "high", "low", "close", "volume"]
    df[numeric_columns] = df[numeric_columns].astype(float)
    return df[["timestamp", "datetime", "open", "high", "low", "close", "volume"]]


def add_moving_averages(df: pd.DataFrame, short: int = 7, mid: int = 25, long: int = 99) -> pd.DataFrame:
    df = df.copy()
    df["ma7"] = df["close"].rolling(short).mean()
    df["ma25"] = df["close"].rolling(mid).mean()
    df["ma99"] = df["close"].rolling(long).mean()
    return df


def add_volume_averages(df: pd.DataFrame, ma_bars: int = 5) -> pd.DataFrame:
    df = df.copy()
    df["vol_ma5"] = df["volume"].rolling(ma_bars).mean()
    df["vol_ma10"] = df["volume"].rolling(10).mean()
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    df = df.copy()
    close = df["close"]
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    df["dif"] = ema_fast - ema_slow
    df["dea"] = df["dif"].ewm(span=signal, adjust=False).mean()
    df["hist"] = df["dif"] - df["dea"]
    return df


def add_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    ma_cfg = cfg.get("ma", {})
    macd_cfg = cfg.get("macd", {})
    volume_cfg = cfg.get("volume", {})
    df = add_moving_averages(
        df,
        short=int(ma_cfg.get("short", 7)),
        mid=int(ma_cfg.get("mid", 25)),
        long=int(ma_cfg.get("long", 99)),
    )
    df = add_volume_averages(df, ma_bars=int(volume_cfg.get("ma_bars", 5)))
    df = add_macd(
        df,
        fast=int(macd_cfg.get("fast", 12)),
        slow=int(macd_cfg.get("slow", 26)),
        signal=int(macd_cfg.get("signal", 9)),
    )
    return df
