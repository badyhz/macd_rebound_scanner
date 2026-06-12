from __future__ import annotations

import os
import time
from typing import Any

import ccxt


def normalize_symbol(symbol: str) -> str:
    """
    Convert ETHUSDT to the Binance USDT-M futures symbol ETH/USDT:USDT.
    If the input already looks like a ccxt futures symbol, return it unchanged.
    """
    cleaned = symbol.strip().upper()
    if "/" in cleaned and ":" in cleaned:
        return cleaned
    if "/" in cleaned and cleaned.endswith("/USDT"):
        return f"{cleaned}:USDT"
    if cleaned.endswith("USDT") and len(cleaned) > 4:
        base = cleaned[:-4]
        return f"{base}/USDT:USDT"
    return cleaned


def display_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if "/" in cleaned:
        return cleaned.split("/")[0] + "USDT"
    return cleaned


def list_usdt_perpetual_symbols(exchange: Any) -> list[str]:
    """
    Return Binance USDT-M futures symbols that are TRADING perpetual contracts.
    Symbols are returned as display symbols such as BTCUSDT.
    """
    markets = exchange.load_markets()
    selected: list[str] = []
    for market in markets.values():
        info = market.get("info", {})
        quote = market.get("quote") or info.get("quoteAsset")
        status = info.get("status") or market.get("status")
        contract_type = info.get("contractType")
        is_swap = bool(market.get("swap"))
        is_linear = bool(market.get("linear"))

        if quote != "USDT":
            continue
        if status != "TRADING":
            continue
        if contract_type and contract_type != "PERPETUAL":
            continue
        if not is_swap or not is_linear:
            continue
        selected.append(display_symbol(market["symbol"]))

    return sorted(set(selected))


def create_exchange() -> ccxt.binance:
    exchange_config: dict[str, Any] = {
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
            "defaultSubType": "linear",
            "fetchMarkets": {"types": ["linear"]},
        },
    }

    proxies = {
        "http": os.getenv("HTTP_PROXY") or os.getenv("http_proxy"),
        "https": os.getenv("HTTPS_PROXY") or os.getenv("https_proxy"),
    }
    proxies = {key: value for key, value in proxies.items() if value}
    if proxies:
        exchange_config["proxies"] = proxies

    return ccxt.binance(exchange_config)


def timeframe_to_milliseconds(interval: str) -> int:
    unit = interval[-1]
    amount = int(interval[:-1])
    factors = {
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
        "w": 7 * 24 * 60 * 60 * 1000,
    }
    if unit not in factors:
        raise ValueError(f"Unsupported interval: {interval}")
    return amount * factors[unit]


def fetch_ohlcv(
    exchange: Any,
    symbol: str,
    interval: str,
    limit: int,
    use_closed_candle_only: bool = True,
) -> list[list[float]]:
    request_limit = limit + 1 if use_closed_candle_only else limit
    ohlcv = exchange.fetch_ohlcv(normalize_symbol(symbol), timeframe=interval, limit=request_limit)
    if not use_closed_candle_only or not ohlcv:
        return ohlcv[-limit:]

    now_ms = int(time.time() * 1000)
    interval_ms = timeframe_to_milliseconds(interval)
    last_open_time = int(ohlcv[-1][0])
    if last_open_time + interval_ms > now_ms:
        ohlcv = ohlcv[:-1]
    return ohlcv[-limit:]
