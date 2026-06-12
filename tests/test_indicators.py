import pandas as pd

from src.indicators import add_indicators, add_macd, add_moving_averages, add_volume_averages, ohlcv_to_dataframe


def test_ohlcv_to_dataframe_columns_and_types():
    ohlcv = [[1700000000000, 1, 2, 0.5, 1.5, 100]]
    df = ohlcv_to_dataframe(ohlcv)

    assert list(df.columns) == ["timestamp", "datetime", "open", "high", "low", "close", "volume"]
    assert df.loc[0, "timestamp"] == 1700000000000
    assert pd.api.types.is_datetime64_any_dtype(df["datetime"])
    assert df.loc[0, "close"] == 1.5


def test_moving_averages_are_correct():
    df = pd.DataFrame({"close": range(1, 101), "volume": range(101, 201)})
    df = add_moving_averages(df)
    df = add_volume_averages(df)

    assert df["ma7"].iloc[-1] == sum(range(94, 101)) / 7
    assert df["ma25"].iloc[-1] == sum(range(76, 101)) / 25
    assert df["ma99"].iloc[-1] == sum(range(2, 101)) / 99
    assert df["vol_ma5"].iloc[-1] == sum(range(196, 201)) / 5
    assert df["vol_ma10"].iloc[-1] == sum(range(191, 201)) / 10


def test_macd_outputs_expected_fields():
    df = pd.DataFrame({"close": [float(i) for i in range(1, 80)]})
    df = add_macd(df)

    assert {"dif", "dea", "hist"}.issubset(df.columns)
    assert not df[["dif", "dea", "hist"]].iloc[-1].isna().any()
    assert df["hist"].iloc[-1] == df["dif"].iloc[-1] - df["dea"].iloc[-1]


def test_add_indicators_uses_configured_fields():
    df = pd.DataFrame({"close": range(1, 120), "volume": range(1, 120)})
    cfg = {
        "ma": {"short": 7, "mid": 25, "long": 99},
        "volume": {"ma_bars": 5},
        "macd": {"fast": 12, "slow": 26, "signal": 9},
    }
    result = add_indicators(df, cfg)

    assert {"ma7", "ma25", "ma99", "vol_ma5", "vol_ma10", "dif", "dea", "hist"}.issubset(result.columns)
