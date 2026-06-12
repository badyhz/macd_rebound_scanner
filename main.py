from __future__ import annotations

import argparse
import logging
import sys

from src.config import load_config, resolve_path
from src.scheduler import run_loop


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Feishu MACD rebound scanner for Binance USDT-M Futures")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Log alerts without sending Feishu messages")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    parser.add_argument("--symbol", help="Scan a single symbol, e.g. ETHUSDT")
    parser.add_argument("--interval", help="Scan a single interval, e.g. 5m")
    return parser.parse_args()


def setup_logging(cfg: dict) -> None:
    log_path = resolve_path(cfg, cfg["paths"]["log_file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    setup_logging(cfg)
    logging.info("程序启动")
    logging.info("配置加载成功: %s", args.config)
    if args.dry_run:
        logging.info("dry-run 模式启用，不会真实发送飞书")

    run_loop(
        cfg,
        dry_run=args.dry_run,
        symbol_override=args.symbol,
        interval_override=args.interval,
        once=args.once,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
