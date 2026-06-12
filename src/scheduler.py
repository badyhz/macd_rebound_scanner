from __future__ import annotations

import logging
import os
import time
import traceback
from datetime import datetime
from typing import Any

from .config import resolve_path
from .exchange_client import create_exchange, display_symbol, fetch_ohlcv, list_usdt_perpetual_symbols
from .heartbeat import send_runtime_heartbeat, send_start_heartbeat, should_send_runtime_heartbeat
from .indicators import add_indicators, ohlcv_to_dataframe
from .jsonl_logger import append_jsonl
from .notifier_feishu import format_signal_message, send_feishu_text
from .signal_logger import append_signal
from .state_store import AlertStateStore, make_alert_key
from .strategy import evaluate_macd_rebound


logger = logging.getLogger(__name__)


def _selected_symbols(cfg: dict[str, Any], symbol_override: str | None) -> list[str]:
    if symbol_override:
        return [symbol_override.upper()]
    return [str(symbol).upper() for symbol in cfg["scan"].get("symbols", [])]


def _load_symbols(cfg: dict[str, Any], exchange: Any, symbol_override: str | None) -> tuple[list[str], int, str]:
    if symbol_override:
        symbols = [symbol_override.upper()]
        return symbols, len(symbols), "override"

    scan_cfg = cfg["scan"]
    if not bool(scan_cfg.get("all_usdt_perpetual", False)):
        symbols = _selected_symbols(cfg, symbol_override)
        return symbols, len(symbols), "config"

    all_symbols = list_usdt_perpetual_symbols(exchange)
    excluded = {str(symbol).upper() for symbol in scan_cfg.get("exclude_symbols", [])}
    symbols = [symbol for symbol in all_symbols if symbol not in excluded]
    if bool(scan_cfg.get("exclude_non_ascii_symbols", True)):
        before_ascii_filter = len(symbols)
        symbols = [symbol for symbol in symbols if symbol.isascii()]
        logger.info("排除非 ASCII 交易对: removed=%s", before_ascii_filter - len(symbols))
    max_symbols = scan_cfg.get("max_symbols")
    if max_symbols:
        symbols = symbols[: int(max_symbols)]
    logger.info(
        "本轮加载 Binance USDT-M 永续合约交易对: total=%s, selected=%s, excluded=%s",
        len(all_symbols),
        len(symbols),
        len(excluded),
    )
    return symbols, len(all_symbols), "binance_um_futures"


def _selected_intervals(cfg: dict[str, Any], interval_override: str | None) -> list[str]:
    if interval_override:
        return [interval_override]
    return [str(interval) for interval in cfg["scan"].get("intervals", ["15m"])]


def scan_once(
    cfg: dict[str, Any],
    dry_run: bool = False,
    symbol_override: str | None = None,
    interval_override: str | None = None,
    exchange: Any | None = None,
    return_summary: bool = False,
) -> dict[str, int] | tuple[dict[str, int], dict[str, Any]]:
    round_started = time.monotonic()
    round_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    logger.info("开始一轮扫描 round_id=%s dry_run=%s", round_id, dry_run)
    exchange = exchange or create_exchange()
    state_path = resolve_path(cfg, cfg["paths"]["state_file"])
    signals_path = resolve_path(cfg, cfg["paths"]["signals_csv"])
    scan_detail_path = resolve_path(cfg, cfg["paths"].get("scan_detail_jsonl", "logs/scan_detail.jsonl"))
    alerts_path = resolve_path(cfg, cfg["paths"].get("alerts_jsonl", "logs/alerts.jsonl"))
    errors_path = resolve_path(cfg, cfg["paths"].get("errors_log", "logs/errors.log"))
    state_store = AlertStateStore(state_path)

    stats = {"scanned": 0, "triggered": 0, "alerted": 0, "cooldown_skipped": 0, "errors": 0}
    try:
        symbols, symbols_total, symbols_source = _load_symbols(cfg, exchange, symbol_override)
    except Exception:
        stats["errors"] += 1
        logger.exception("加载交易对失败 round_id=%s", round_id)
        errors_path.parent.mkdir(parents=True, exist_ok=True)
        errors_path.write_text(traceback.format_exc(), encoding="utf-8")
        if return_summary:
            summary = {
                "round_id": round_id,
                "market": "unknown",
                "timeframe": ",".join(_selected_intervals(cfg, interval_override)),
                "symbols_total": 0,
                "symbols_scanned": stats["scanned"],
                "triggered": stats["triggered"],
                "alerted": stats["alerted"],
                "cooldown_skipped": stats["cooldown_skipped"],
                "errors": stats["errors"],
                "duration_seconds": round(time.monotonic() - round_started, 2),
            }
            return stats, summary
        return stats

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
                    append_jsonl(
                        scan_detail_path,
                        {
                            "round_id": round_id,
                            "symbol": symbol,
                            "interval": interval,
                            "triggered": False,
                            "failed_conditions": evaluation["failed_conditions"],
                            "metrics": evaluation.get("metrics", {}),
                        },
                    )
                    continue

                stats["triggered"] += 1
                logger.info("%s %s 触发B级信号: %s", symbol, interval, "；".join(evaluation["reason"]))
                append_jsonl(
                    scan_detail_path,
                    {
                        "round_id": round_id,
                        "symbol": symbol,
                        "interval": interval,
                        "triggered": True,
                        "reason": evaluation["reason"],
                        "metrics": evaluation.get("metrics", {}),
                    },
                )

                key = make_alert_key(symbol, interval, strategy_cfg.get("name", "macd_rebound"))
                can_alert, cooldown_reason = state_store.can_alert(key, cooldown_minutes)
                if not can_alert:
                    stats["cooldown_skipped"] += 1
                    logger.info("%s cooldown 命中，跳过报警: %s", key, cooldown_reason)
                    append_jsonl(
                        alerts_path,
                        {
                            "round_id": round_id,
                            "symbol": symbol,
                            "interval": interval,
                            "signal_time": candle_time,
                            "sent": False,
                            "skipped": "cooldown",
                            "signal_source": "real_signal",
                            "error_message": cooldown_reason,
                        },
                    )
                    continue

                append_signal(signals_path, symbol, interval, candle_time, evaluation)
                message = format_signal_message(
                    symbol,
                    interval,
                    candle_time,
                    evaluation,
                    round_id=round_id,
                    signal_source="real_signal",
                    cooldown_skipped=False,
                )

                if dry_run:
                    logger.info("dry-run: 本应报警但跳过真实飞书发送\n%s", message)
                    stats["alerted"] += 1
                    append_jsonl(
                        alerts_path,
                        {
                            "round_id": round_id,
                            "symbol": symbol,
                            "interval": interval,
                            "signal_time": candle_time,
                            "sent": False,
                            "dry_run": True,
                            "signal_source": "real_signal",
                            "webhook_http_status": None,
                            "error_message": None,
                        },
                    )
                    continue

                if not webhook_url:
                    logger.warning("未配置 FEISHU_WEBHOOK_URL，跳过真实发送")
                    append_jsonl(
                        alerts_path,
                        {
                            "round_id": round_id,
                            "symbol": symbol,
                            "interval": interval,
                            "signal_time": candle_time,
                            "sent": False,
                            "signal_source": "real_signal",
                            "webhook_http_status": None,
                            "error_message": "FEISHU_WEBHOOK_URL is empty",
                        },
                    )
                    continue

                response = send_feishu_text(webhook_url, message, secret=secret)
                state_store.record_alert(key, evaluation["metrics"]["price"])
                stats["alerted"] += 1
                logger.info("%s 飞书发送成功 feishu_status=success http_status=%s sent=true", key, response.get("_http_status"))
                append_jsonl(
                    alerts_path,
                    {
                        "round_id": round_id,
                        "symbol": symbol,
                        "interval": interval,
                        "signal_time": candle_time,
                        "sent": True,
                        "signal_source": "real_signal",
                        "webhook_http_status": response.get("_http_status"),
                        "response": response,
                        "error_message": None,
                    },
                )
            except Exception:
                stats["errors"] += 1
                logger.exception("%s %s 扫描异常", symbol, interval)
                append_jsonl(
                    scan_detail_path,
                    {
                        "round_id": round_id,
                        "symbol": symbol,
                        "interval": interval,
                        "triggered": False,
                        "error": traceback.format_exc(),
                    },
                )
                errors_path.parent.mkdir(parents=True, exist_ok=True)
                with errors_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"\n[{datetime.now().isoformat()}] round_id={round_id} symbol={symbol} interval={interval}\n")
                    handle.write(traceback.format_exc())

    duration_seconds = time.monotonic() - round_started
    summary = {
        "round_id": round_id,
        "market": symbols_source,
        "timeframe": ",".join(intervals),
        "symbols_total": symbols_total,
        "symbols_scanned": stats["scanned"],
        "triggered": stats["triggered"],
        "alerted": stats["alerted"],
        "cooldown_skipped": stats["cooldown_skipped"],
        "errors": stats["errors"],
        "duration_seconds": round(duration_seconds, 2),
    }
    logger.info("本轮扫描结束: %s summary=%s", stats, summary)
    if return_summary:
        return stats, summary
    return stats


def send_force_alert(cfg: dict[str, Any], symbol: str, interval: str = "15m", dry_run: bool = False) -> dict[str, Any]:
    webhook_url = os.getenv(cfg["alert"].get("webhook_url_env", "FEISHU_WEBHOOK_URL"), "")
    secret = os.getenv(cfg["alert"].get("secret_env", "FEISHU_SECRET")) or None
    alerts_path = resolve_path(cfg, cfg["paths"].get("alerts_jsonl", "logs/alerts.jsonl"))
    round_id = datetime.now().strftime("%Y%m%d-%H%M%S-force")
    content = (
        "【MACD扫描器测试提醒】\n"
        f"round_id: {round_id}\n"
        f"symbol: {symbol.upper()}\n"
        f"周期：{interval}\n"
        "信号来源: force_alert\n"
        "是否冷却跳过: 否\n"
        "mode: force_test\n"
        "result: 飞书链路正常"
    )
    payload = {
        "round_id": round_id,
        "symbol": symbol.upper(),
        "interval": interval,
        "signal_time": datetime.now(),
        "signal_source": "force_alert",
        "force_alert": True,
        "dry_run": dry_run,
    }
    if dry_run:
        payload.update({"sent": False, "webhook_http_status": None, "error_message": None})
        append_jsonl(alerts_path, payload)
        logger.info("force-alert dry-run sent=false symbol=%s", symbol.upper())
        return payload
    if not webhook_url:
        payload.update({"sent": False, "webhook_http_status": None, "error_message": "FEISHU_WEBHOOK_URL is empty"})
        append_jsonl(alerts_path, payload)
        logger.error("force-alert sent=false error=FEISHU_WEBHOOK_URL is empty")
        return payload

    try:
        response = send_feishu_text(webhook_url, content, secret=secret)
        payload.update({"sent": True, "webhook_http_status": response.get("_http_status"), "response": response, "error_message": None})
        logger.info("force-alert sent=true symbol=%s webhook_http_status=%s", symbol.upper(), response.get("_http_status"))
    except Exception as exc:
        payload.update({"sent": False, "webhook_http_status": None, "error_message": str(exc)})
        logger.exception("force-alert sent=false symbol=%s", symbol.upper())
    append_jsonl(alerts_path, payload)
    return payload


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
    logger.info("dry_run=%s", dry_run)
    if dry_run:
        logger.info("Feishu notifier disabled by dry-run")
    elif os.getenv(cfg["alert"].get("webhook_url_env", "FEISHU_WEBHOOK_URL"), ""):
        logger.info("Feishu notifier enabled")
    else:
        logger.warning("Feishu notifier disabled: webhook env is empty")

    send_start_heartbeat(cfg, dry_run=dry_run, interval_override=interval_override)
    round_count = 0
    while True:
        loop_started = time.monotonic()
        stats, summary = scan_once(
            cfg,
            dry_run=dry_run,
            symbol_override=symbol_override,
            interval_override=interval_override,
            exchange=exchange,
            return_summary=True,
        )
        round_count += 1
        if should_send_runtime_heartbeat(cfg, round_count):
            send_runtime_heartbeat(cfg, summary, dry_run=dry_run)
        if once:
            return
        sleep_seconds = int(cfg["scan"].get("loop_seconds", 120))
        logger.info("等待 %s 秒后开始下一轮扫描 next_scan_after=%ss elapsed=%.2fs", sleep_seconds, sleep_seconds, time.monotonic() - loop_started)
        time.sleep(sleep_seconds)
