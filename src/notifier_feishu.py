from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import datetime
from typing import Any

import requests


def gen_feishu_sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_feishu_text(webhook_url: str, content: str, secret: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": content},
    }
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = gen_feishu_sign(secret, timestamp)

    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        data["_http_status"] = resp.status_code
    return data


def _fmt_number(value: Any, decimals: int = 4) -> str:
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "NA"


def _fmt_volume(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "NA"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    if abs(number) >= 1_000:
        return f"{number / 1_000:.2f}K"
    return f"{number:.2f}"


def format_signal_message(
    symbol: str,
    interval: str,
    candle_time: datetime | str,
    evaluation: dict[str, Any],
) -> str:
    metrics = evaluation.get("metrics", {})
    reason = evaluation.get("reason", [])
    if hasattr(candle_time, "strftime"):
        candle_time_text = candle_time.strftime("%Y-%m-%d %H:%M:%S")
    else:
        candle_time_text = str(candle_time)

    reason_text = "\n".join(f"{index}. {item}" for index, item in enumerate(reason, start=1))
    above_ma99 = "是" if metrics.get("above_ma99") else "否"

    return f"""【短线反弹启动信号】

交易对：{symbol}
周期：{interval}
信号级别：B级
当前价格：{_fmt_number(metrics.get("price"), 4)}
K线时间：{candle_time_text}

触发原因：
{reason_text}

指标数据：
DIF：{_fmt_number(metrics.get("dif"), 4)}
DEA：{_fmt_number(metrics.get("dea"), 4)}
MACD柱：{_fmt_number(metrics.get("hist"), 4)}
MA7：{_fmt_number(metrics.get("ma7"), 4)}
MA25：{_fmt_number(metrics.get("ma25"), 4)}
MA99：{_fmt_number(metrics.get("ma99"), 4)}
成交量：{_fmt_volume(metrics.get("volume"))}
VOL_MA5：{_fmt_volume(metrics.get("volume_ma5"))}
量比：{_fmt_number(metrics.get("volume_ratio"), 2)}
是否站上MA99：{above_ma99}

策略解释：
下跌后空头动能衰竭，MACD二次转多，价格放量突破短期均线，可能进入短线反弹阶段。

风险提示：
该信号不是直接追多指令，需要结合上方压力位、止损位、大周期趋势和BTC整体走势确认。"""
