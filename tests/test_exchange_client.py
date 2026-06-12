from src import exchange_client


def test_create_exchange_uses_proxy_env(monkeypatch):
    captured = {}

    def fake_binance(config):
        captured.update(config)
        return object()

    monkeypatch.setattr(exchange_client.ccxt, "binance", fake_binance)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")

    exchange_client.create_exchange()

    assert captured["proxies"] == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }


def test_create_exchange_supports_authenticated_http_proxy(monkeypatch):
    captured = {}

    def fake_binance(config):
        captured.update(config)
        return object()

    monkeypatch.setattr(exchange_client.ccxt, "binance", fake_binance)
    monkeypatch.setenv("HTTP_PROXY", "http://user:pass@192.168.31.1:7890")
    monkeypatch.setenv("HTTPS_PROXY", "http://user:pass@192.168.31.1:7890")

    exchange_client.create_exchange()

    assert captured["proxies"] == {
        "http": "http://user:pass@192.168.31.1:7890",
        "https": "http://user:pass@192.168.31.1:7890",
    }


def test_create_exchange_supports_socks5h_proxy(monkeypatch):
    captured = {}

    def fake_binance(config):
        captured.update(config)
        return object()

    monkeypatch.setattr(exchange_client.ccxt, "binance", fake_binance)
    monkeypatch.setenv("HTTP_PROXY", "socks5h://192.168.31.1:7891")
    monkeypatch.setenv("HTTPS_PROXY", "socks5h://192.168.31.1:7891")

    exchange_client.create_exchange()

    assert captured["proxies"] == {
        "http": "socks5h://192.168.31.1:7891",
        "https": "socks5h://192.168.31.1:7891",
    }


def test_create_exchange_omits_empty_proxy_env(monkeypatch):
    captured = {}

    def fake_binance(config):
        captured.update(config)
        return object()

    monkeypatch.setattr(exchange_client.ccxt, "binance", fake_binance)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)

    exchange_client.create_exchange()

    assert "proxies" not in captured


def test_list_usdt_perpetual_symbols_filters_markets():
    class FakeExchange:
        def load_markets(self):
            return {
                "BTC/USDT:USDT": {
                    "symbol": "BTC/USDT:USDT",
                    "quote": "USDT",
                    "swap": True,
                    "linear": True,
                    "info": {"status": "TRADING", "contractType": "PERPETUAL", "quoteAsset": "USDT"},
                },
                "ETH/USDC:USDC": {
                    "symbol": "ETH/USDC:USDC",
                    "quote": "USDC",
                    "swap": True,
                    "linear": True,
                    "info": {"status": "TRADING", "contractType": "PERPETUAL", "quoteAsset": "USDC"},
                },
                "OLD/USDT:USDT": {
                    "symbol": "OLD/USDT:USDT",
                    "quote": "USDT",
                    "swap": True,
                    "linear": True,
                    "info": {"status": "BREAK", "contractType": "PERPETUAL", "quoteAsset": "USDT"},
                },
                "BTC/USDT": {
                    "symbol": "BTC/USDT",
                    "quote": "USDT",
                    "swap": False,
                    "linear": False,
                    "info": {"status": "TRADING", "quoteAsset": "USDT"},
                },
            }

    assert exchange_client.list_usdt_perpetual_symbols(FakeExchange()) == ["BTCUSDT"]
