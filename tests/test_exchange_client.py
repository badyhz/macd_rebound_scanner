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
