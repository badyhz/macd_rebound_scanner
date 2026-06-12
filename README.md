# MACD Rebound Scanner

Feishu 飞书版 Binance USDT-M Futures 短线 MACD 反弹扫描报警器。

第一版只做行情扫描和报警，不包含实盘下单逻辑。

## 功能

- Binance USDT-M Futures K线扫描
- 默认动态扫描 Binance USDT-M Futures `TRADING + PERPETUAL + USDT` 合约
- 默认周期 `5m`
- 只使用已收盘 K 线判断信号
- 计算 MA7 / MA25 / MA99 / VOL_MA5 / VOL_MA10 / MACD
- 识别 B 级 MACD 空头衰竭短线反弹信号
- 飞书机器人通知，支持签名 secret
- `data/alert_state.json` 防重复报警
- `data/signals.csv` 记录信号
- `logs/macd_rebound_scanner.log` 记录运行日志
- `logs/scan_detail.jsonl` 记录每个交易对的判断结果
- `logs/alerts.jsonl` 记录所有触发和飞书发送结果
- `logs/errors.log` 记录异常
- 支持 `--dry-run` 和 `--once`

## 安装

```bash
cd macd_rebound_scanner
pip install -r requirements.txt
```

## 运行

```bash
python main.py --config config.yaml
```

只跑一轮并且不发送飞书：

```bash
python main.py --config config.yaml --once --dry-run
```

单币种测试：

```bash
python main.py --config config.yaml --symbol ETHUSDT --interval 5m --once --dry-run
```

默认 `config.yaml` 中 `scan.all_usdt_perpetual: true`，每轮会从 Binance USDT-M markets 动态加载全部 `TRADING + PERPETUAL + USDT` 交易对。要临时只扫一个交易对，用 `--symbol` 覆盖；要只扫配置中的固定列表，可把 `scan.all_usdt_perpetual` 改为 `false`。

默认 `scan.exclude_non_ascii_symbols: true`，会排除少量非 ASCII 合约名，避免异常展示名进入生产提醒。

如果当前网络需要本地代理访问 Binance futures API，可以在命令前设置代理环境变量：

```bash
HTTP_PROXY=http://127.0.0.1:7890 \
HTTPS_PROXY=http://127.0.0.1:7890 \
python main.py --config config.yaml --symbol ETHUSDT --interval 5m --once --dry-run
```

环境变量为空时，程序不会给 ccxt 设置代理。

OpenWrt / Mihomo / OpenClash 常见代理方式：

```bash
# HTTP 代理，无认证
HTTP_PROXY=http://192.168.31.1:7890 \
HTTPS_PROXY=http://192.168.31.1:7890 \
python main.py --config config.yaml --symbol ETHUSDT --interval 5m --once --dry-run

# HTTP 代理，Basic 认证。用户名或密码有特殊字符时需要 URL encode。
HTTP_PROXY=http://用户名:密码@192.168.31.1:7890 \
HTTPS_PROXY=http://用户名:密码@192.168.31.1:7890 \
python main.py --config config.yaml --symbol ETHUSDT --interval 5m --once --dry-run

# SOCKS5H 代理，DNS 也交给代理处理。
HTTP_PROXY=socks5h://192.168.31.1:7891 \
HTTPS_PROXY=socks5h://192.168.31.1:7891 \
python main.py --config config.yaml --symbol ETHUSDT --interval 5m --once --dry-run
```

如果 `curl -x http://192.168.31.1:7890 -Iv https://fapi.binance.com/fapi/v1/exchangeInfo` 返回 `407 Proxy Authentication Required`，说明代理端口已连通，但 OpenClash/Mihomo 开启了代理认证。需要填入认证账号密码，或在 OpenClash/Mihomo 中关闭 LAN 代理认证，并确保代理端口只在局域网内可用。

## 飞书环境变量

```bash
export FEISHU_WEBHOOK_URL="你的飞书机器人 webhook"
export FEISHU_SECRET="你的飞书机器人签名密钥，如未开启签名则不填"

python main.py --config config.yaml --once
```

单独测试飞书链路：

```bash
python scripts/test_feishu.py
```

强制发送一条测试提醒，不依赖策略触发：

```bash
python main.py --config config.yaml --once --force-alert BTCUSDT
```

如果加 `--dry-run`，只写日志，不会真实发送飞书。

## 测试

```bash
pytest -q
python -m compileall -q main.py src tests
```

不要用 `python -m compileall -q .` 做部署验收；它会递归编译 `.venv/site-packages`，可能被第三方包内部文件影响。这里只需要编译本项目的 `main.py`、`src/` 和 `tests/`。

上线前验收建议：

```bash
python scripts/test_feishu.py
python main.py --config config.yaml --once --dry-run
python main.py --config config.yaml --once --force-alert BTCUSDT
tail -n 100 logs/macd_rebound_scanner.log
tail -n 20 logs/alerts.jsonl
tail -n 20 logs/scan_detail.jsonl
```

部署模板：

```bash
cp deploy/systemd/macd-rebound-scanner.service /etc/systemd/system/macd-rebound-scanner.service
cp deploy/logrotate.d/macd-rebound-scanner /etc/logrotate.d/macd-rebound-scanner
systemctl daemon-reload
systemctl enable macd-rebound-scanner
systemctl restart macd-rebound-scanner
```

## 策略说明

B 级信号需要同时满足：

1. 最近48根K线最高价到最低价跌幅至少 1.5%
2. 当前价格没有明显跌破最近12根低点
3. MACD 前3根负柱连续缩小
4. 当前 MACD 柱由负转正
5. 当前 K 线为阳线，且收盘价高于上一根收盘价
6. 当前收盘价站上 MA7 和 MA25
7. 当前成交量大于 VOL_MA5 的 1.3 倍

风险提示：该信号不是直接追多指令，需要结合压力位、止损位、大周期趋势和 BTC 整体走势确认。
