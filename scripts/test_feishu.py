from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.notifier_feishu import send_feishu_text


def main() -> int:
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "")
    secret = os.getenv("FEISHU_SECRET") or None
    if not webhook_url:
        print("sent=false error=FEISHU_WEBHOOK_URL is empty")
        return 2

    content = "【MACD扫描器测试提醒】\nsymbol: BTCUSDT\n周期：15m\nmode: force_test\nresult: 飞书链路正常"
    try:
        response = send_feishu_text(webhook_url, content, secret=secret)
    except Exception as exc:
        print(f"sent=false error={exc}")
        return 1

    print(f"sent=true http_status={response.get('_http_status')} response={response}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
