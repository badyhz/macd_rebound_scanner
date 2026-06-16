from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
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


def feishu_response_success(response: dict[str, Any]) -> bool:
    if "code" in response:
        return str(response.get("code")) == "0"
    if "StatusCode" in response:
        return str(response.get("StatusCode")) == "0"
    return True


def feishu_response_error_message(response: dict[str, Any]) -> str:
    code = response.get("code", response.get("StatusCode", "NA"))
    message = response.get("msg") or response.get("StatusMessage") or "Feishu response is not successful"
    return f"Feishu response code={code} msg={message}"


def _fmt_number(value: Any, decimals: int = 4) -> str:
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "NA"


def _price_decimals(price: Any) -> int:
    try:
        number = abs(float(price))
    except (TypeError, ValueError):
        return 4
    if number < 0.1:
        return 8
    if number < 1:
        return 6
    return 4


def _fmt_price_relative(value: Any, price: Any) -> str:
    return _fmt_number(value, _price_decimals(price))


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


def _format_candle_times(candle_time: datetime | str) -> tuple[str, str]:
    if isinstance(candle_time, datetime):
        utc_time = candle_time
    else:
        try:
            utc_time = datetime.fromisoformat(str(candle_time))
        except ValueError:
            return str(candle_time), "NA"

    if utc_time.tzinfo is None:
        utc_time = utc_time.replace(tzinfo=timezone.utc)
    else:
        utc_time = utc_time.astimezone(timezone.utc)

    beijing_time = utc_time.astimezone(timezone(timedelta(hours=8)))
    return (
        utc_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        beijing_time.strftime("%Y-%m-%d %H:%M:%S UTC+8"),
    )


def _interval_title_label(interval: str) -> str:
    labels = {
        "15m": "15 分钟",
        "1h": "1 小时",
    }
    return labels.get(str(interval), str(interval))


def format_signal_message(
    symbol: str,
    interval: str,
    candle_time: datetime | str,
    evaluation: dict[str, Any],
    *,
    round_id: str | None = None,
    signal_source: str = "real_signal",
    cooldown_skipped: bool = False,
) -> str:
    metrics = evaluation.get("metrics", {})
    reason = evaluation.get("reason", [])
    utc_time_text, beijing_time_text = _format_candle_times(candle_time)

    reason_text = "\n".join(f"{index}. {item}" for index, item in enumerate(reason, start=1))
    above_ma99 = "是" if metrics.get("above_ma99") else "否"
    cooldown_text = "是" if cooldown_skipped else "否"
    price = metrics.get("price")

    return f"""【短线反弹启动信号-{_interval_title_label(interval)}】

round_id：{round_id or "NA"}
信号来源：{signal_source}
是否冷却跳过：{cooldown_text}
交易对：{symbol}
周期：{interval}
信号级别：B级
当前价格：{_fmt_price_relative(price, price)}
K线时间(UTC)：{utc_time_text}
K线时间(北京时间)：{beijing_time_text}

触发原因：
{reason_text}

指标数据：
DIF：{_fmt_price_relative(metrics.get("dif"), price)}
DEA：{_fmt_price_relative(metrics.get("dea"), price)}
MACD柱：{_fmt_price_relative(metrics.get("hist"), price)}
MA7：{_fmt_price_relative(metrics.get("ma7"), price)}
MA25：{_fmt_price_relative(metrics.get("ma25"), price)}
MA99：{_fmt_price_relative(metrics.get("ma99"), price)}
成交量：{_fmt_volume(metrics.get("volume"))}
VOL_MA5：{_fmt_volume(metrics.get("volume_ma5"))}
量比：{_fmt_number(metrics.get("volume_ratio"), 2)}
是否站上MA99：{above_ma99}

策略解释：
下跌后空头动能衰竭，MACD二次转多，价格放量突破短期均线，可能进入短线反弹阶段。

风险提示：
该信号不是直接追多指令，需要结合上方压力位、止损位、大周期趋势和BTC整体走势确认。"""
