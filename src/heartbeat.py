from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import resolve_path
from .jsonl_logger import append_jsonl
from .notifier_feishu import send_feishu_text


logger = logging.getLogger(__name__)
BEIJING_TZ = timezone(timedelta(hours=8))


def heartbeat_enabled(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("heartbeat", {}).get("enabled", False))


def should_send_runtime_heartbeat(cfg: dict[str, Any], round_count: int) -> bool:
    if not heartbeat_enabled(cfg):
        return False
    interval_rounds = int(cfg.get("heartbeat", {}).get("interval_rounds", 120))
    return interval_rounds > 0 and round_count > 0 and round_count % interval_rounds == 0


def _beijing_now_text(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _interval_text(cfg: dict[str, Any], interval_override: str | None = None) -> str:
    if interval_override:
        return interval_override
    return ",".join(str(interval) for interval in cfg.get("scan", {}).get("intervals", ["15m"]))


def _errors_log_line_count(cfg: dict[str, Any]) -> int:
    errors_path = resolve_path(cfg, cfg["paths"].get("errors_log", "logs/errors.log"))
    if not errors_path.exists():
        return 0
    return len(errors_path.read_text(encoding="utf-8", errors="ignore").splitlines())


def _latest_real_alert_time(cfg: dict[str, Any]) -> str:
    alerts_path = resolve_path(cfg, cfg["paths"].get("alerts_jsonl", "logs/alerts.jsonl"))
    if not alerts_path.exists():
        return "无"

    lines = alerts_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in reversed(lines[-2000:]):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        signal_source = payload.get("signal_source")
        alert_type = payload.get("alert_type")
        if payload.get("force_alert"):
            continue
        if alert_type in {"heartbeat", "heartbeat_start"}:
            continue
        if isinstance(signal_source, str) and signal_source.startswith("heartbeat"):
            continue
        if signal_source not in {None, "real_signal"}:
            continue
        if not payload.get("sent"):
            continue
        return str(payload.get("signal_time") or payload.get("round_id") or "无")
    return "无"


def format_start_heartbeat_message(
    cfg: dict[str, Any],
    dry_run: bool,
    *,
    interval_override: str | None = None,
    now: datetime | None = None,
) -> str:
    scan_cfg = cfg.get("scan", {})
    webhook_url = os.getenv(cfg["alert"].get("webhook_url_env", "FEISHU_WEBHOOK_URL"), "")
    feishu_status = "disabled" if dry_run or not webhook_url else "enabled"
    return f"""【MACD扫描器已启动】

状态：running
信号来源：heartbeat_start
dry_run：{dry_run}
市场：Binance USDT-M Futures
全市场扫描：{str(bool(scan_cfg.get("all_usdt_perpetual", False))).lower()}
周期：{_interval_text(cfg, interval_override)}
轮询间隔：{int(scan_cfg.get("loop_seconds", 120))} 秒
飞书提醒：{feishu_status}
启动时间：北京时间 {_beijing_now_text(now)}

说明：
服务已启动，后续触发策略信号会自动推送。"""


def format_runtime_heartbeat_message(
    cfg: dict[str, Any],
    summary: dict[str, Any],
    dry_run: bool,
    *,
    now: datetime | None = None,
) -> str:
    scan_cfg = cfg.get("scan", {})
    return f"""【MACD扫描器心跳】

状态：running
信号来源：heartbeat
round_id：{summary.get("round_id", "NA")}
市场：{summary.get("market", "NA")}
周期：{summary.get("timeframe") or _interval_text(cfg)}

最近一轮：
symbols_total：{summary.get("symbols_total", 0)}
symbols_scanned：{summary.get("symbols_scanned", 0)}
triggered：{summary.get("triggered", 0)}
alerted：{summary.get("alerted", 0)}
cooldown_skipped：{summary.get("cooldown_skipped", 0)}
errors：{summary.get("errors", 0)}
duration_seconds：{summary.get("duration_seconds", 0)}

运行状态：
loop_seconds：{int(scan_cfg.get("loop_seconds", 120))}
dry_run：{dry_run}
最近一次真实提醒：{_latest_real_alert_time(cfg)}
errors.log 行数：{_errors_log_line_count(cfg)}
当前时间：北京时间 {_beijing_now_text(now)}

说明：
扫描器仍在正常运行。没有策略提醒不代表程序停止。"""


def _append_heartbeat_error(cfg: dict[str, Any], label: str) -> None:
    errors_path = resolve_path(cfg, cfg["paths"].get("errors_log", "logs/errors.log"))
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    with errors_path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n[{datetime.now().isoformat()}] {label}\n")
        handle.write(traceback.format_exc())


def _send_heartbeat(
    cfg: dict[str, Any],
    *,
    alert_type: str,
    signal_source: str,
    content: str,
    dry_run: bool,
    round_id: str | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    alerts_path = resolve_path(cfg, cfg["paths"].get("alerts_jsonl", "logs/alerts.jsonl"))
    payload: dict[str, Any] = {
        "alert_type": alert_type,
        "signal_source": signal_source,
        "round_id": round_id,
        "sent": False,
        "dry_run": dry_run,
        "webhook_http_status": None,
        "error_message": None,
    }
    if summary is not None:
        payload["summary"] = summary

    if dry_run:
        append_jsonl(alerts_path, payload)
        logger.info("%s dry-run sent=false", alert_type)
        return payload

    webhook_url = os.getenv(cfg["alert"].get("webhook_url_env", "FEISHU_WEBHOOK_URL"), "")
    secret = os.getenv(cfg["alert"].get("secret_env", "FEISHU_SECRET")) or None
    if not webhook_url:
        payload["error_message"] = "FEISHU_WEBHOOK_URL is empty"
        append_jsonl(alerts_path, payload)
        logger.warning("%s sent=false error=%s", alert_type, payload["error_message"])
        return payload

    try:
        response = send_feishu_text(webhook_url, content, secret=secret)
        payload.update({"sent": True, "webhook_http_status": response.get("_http_status"), "response": response})
        logger.info("%s sent=true webhook_http_status=%s", alert_type, response.get("_http_status"))
    except Exception as exc:
        payload["error_message"] = str(exc)
        append_jsonl(alerts_path, payload)
        _append_heartbeat_error(cfg, alert_type)
        logger.exception("%s sent=false", alert_type)
        return payload

    append_jsonl(alerts_path, payload)
    return payload


def send_start_heartbeat(
    cfg: dict[str, Any],
    dry_run: bool,
    *,
    interval_override: str | None = None,
) -> dict[str, Any] | None:
    heartbeat_cfg = cfg.get("heartbeat", {})
    if not heartbeat_enabled(cfg) or not bool(heartbeat_cfg.get("send_on_start", False)):
        return None
    content = format_start_heartbeat_message(cfg, dry_run, interval_override=interval_override)
    return _send_heartbeat(
        cfg,
        alert_type="heartbeat_start",
        signal_source="heartbeat_start",
        content=content,
        dry_run=dry_run,
    )


def send_runtime_heartbeat(
    cfg: dict[str, Any],
    summary: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any] | None:
    if not heartbeat_enabled(cfg):
        return None
    content = format_runtime_heartbeat_message(cfg, summary, dry_run)
    return _send_heartbeat(
        cfg,
        alert_type="heartbeat",
        signal_source="heartbeat",
        content=content,
        dry_run=dry_run,
        round_id=str(summary.get("round_id", "")),
        summary=summary,
    )
