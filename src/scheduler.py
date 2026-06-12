from __future__ import annotations

import logging
import os
import time
from typing import Any

from .config import resolve_path
from .exchange_client import create_exchange, display_symbol, fetch_ohlcv
from .indicators import add_indicators, ohlcv_to_dataframe
from .notifier_feishu import format_signal_message, send_feishu_text
from .signal_logger import append_signal
from .state_store import AlertStateStore, make_alert_key
from .strategy import evaluate_macd_rebound


logger = logging.getLogger(__name__)


def _selected_symbols(cfg: dict[str, Any], symbol_override: str | None) -> list[str]:
    if symbol_override:
        return [symbol_override.upper()]
    return [str(symbol).upper() for symbol in cfg["scan"].get("symbols", [])]


def _selected_intervals(cfg: dict[str, Any], interval_override: str | None) -> list[str]:
    if interval_override:
        return [interval_override]
    return [str(interval) for interval in cfg["scan"].get("intervals", ["5m"])]


def scan_once(
    cfg: dict[str, Any],
    dry_run: bool = False,
    symbol_override: str | None = None,
    interval_override: str | None = None,
    exchange: Any | None = None,
) -> dict[str, int]:
    logger.info("开始一轮扫描")
    exchange = exchange or create_exchange()
    state_path = resolve_path(cfg, cfg["paths"]["state_file"])
    signals_path = resolve_path(cfg, cfg["paths"]["signals_csv"])
    state_store = AlertStateStore(state_path)

    stats = {"scanned": 0, "triggered": 0, "alerted": 0, "cooldown_skipped": 0, "errors": 0}
    symbols = _selected_symbols(cfg, symbol_override)
    intervals = _selected_intervals(cfg, interval_override)
    strategy_cfg = cfg["strategy"]
    cooldown_minutes = int(cfg["alert"].get("cooldown_minutes", 30))
    webhook_url = os.getenv(cfg["alert"].get("webhook_url_env", "FEISHU_WEBHOOK_URL"), "")
    secret = os.getenv(cfg["alert"].get("secret_env", "FEISHU_SECRET")) or None

    for interval in intervals:
        for raw_symbol in symbols:
            symbol = display_symbol(raw_symbol)
            stats["scanned"] += 1
            try:
                logger.info("扫描 %s %s", symbol, interval)
                ohlcv = fetch_ohlcv(
                    exchange,
                    raw_symbol,
                    interval,
                    int(cfg["scan"].get("ohlcv_limit", 150)),
                    bool(cfg["scan"].get("use_closed_candle_only", True)),
                )
                if not ohlcv:
                    logger.warning("%s %s 未获取到K线数据", symbol, interval)
                    continue

                df = ohlcv_to_dataframe(ohlcv)
                df = add_indicators(df, strategy_cfg)
                evaluation = evaluate_macd_rebound(df, strategy_cfg)
                latest = df.iloc[-1]
                candle_time = latest["datetime"].to_pydatetime()

                if not evaluation["triggered"]:
                    logger.info(
                        "%s %s 未触发: %s",
                        symbol,
                        interval,
                        "；".join(evaluation["failed_conditions"]),
                    )
                    continue

                stats["triggered"] += 1
                logger.info("%s %s 触发B级信号: %s", symbol, interval, "；".join(evaluation["reason"]))

                key = make_alert_key(symbol, interval, strategy_cfg.get("name", "macd_rebound"))
                can_alert, cooldown_reason = state_store.can_alert(key, cooldown_minutes)
                if not can_alert:
                    stats["cooldown_skipped"] += 1
                    logger.info("%s cooldown 命中，跳过报警: %s", key, cooldown_reason)
                    continue

                append_signal(signals_path, symbol, interval, candle_time, evaluation)
                message = format_signal_message(symbol, interval, candle_time, evaluation)

                if dry_run:
                    logger.info("dry-run: 本应报警但跳过真实飞书发送\n%s", message)
                    stats["alerted"] += 1
                    continue

                if not webhook_url:
                    logger.warning("未配置 FEISHU_WEBHOOK_URL，跳过真实发送")
                    continue

                send_feishu_text(webhook_url, message, secret=secret)
                state_store.record_alert(key, evaluation["metrics"]["price"])
                stats["alerted"] += 1
                logger.info("%s 飞书发送成功", key)
            except Exception:
                stats["errors"] += 1
                logger.exception("%s %s 扫描异常", symbol, interval)

    logger.info("本轮扫描结束: %s", stats)
    return stats


def run_loop(
    cfg: dict[str, Any],
    dry_run: bool = False,
    symbol_override: str | None = None,
    interval_override: str | None = None,
    once: bool = False,
) -> None:
    logger.info("初始化交易所")
    exchange = create_exchange()
    logger.info("交易所初始化成功")

    while True:
        scan_once(
            cfg,
            dry_run=dry_run,
            symbol_override=symbol_override,
            interval_override=interval_override,
            exchange=exchange,
        )
        if once:
            return
        sleep_seconds = int(cfg["scan"].get("loop_seconds", 60))
        logger.info("等待 %s 秒后开始下一轮扫描", sleep_seconds)
        time.sleep(sleep_seconds)
