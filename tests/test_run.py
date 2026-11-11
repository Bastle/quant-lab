"""回测入口测试"""
import sys

import pandas as pd
import pytest

import storage
from backtest import run as run_module


def bar(date: str, close: float = 100.0) -> dict:
    return {"date": date, "open": close - 1.0, "close": close,
            "high": close + 1.0, "low": close - 2.0, "volume": 1000.0}


def test_load_kline_reads_sqlite(tmp_path):
    db = tmp_path / "test.db"
    storage.replace_klines("00700", [bar("2024-01-03", 103.0), bar("2024-01-02", 102.0)], db)

    df = run_module.load_kline("00700", db_path=db)
    assert len(df) == 2
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert pd.api.types.is_datetime64_any_dtype(df["date"])  # 日期转 datetime 供引擎用
    assert df["close"].tolist() == [102.0, 103.0]


def test_load_kline_empty_raises(tmp_path):
    db = tmp_path / "test.db"
    with pytest.raises(FileNotFoundError, match="download_kline"):
        run_module.load_kline("00700", db_path=db)


def test_load_kline_normalizes_code(tmp_path):
    db = tmp_path / "test.db"
    storage.replace_klines("00700", [bar("2024-01-02")], db)
    df = run_module.load_kline("700", db_path=db)  # 不带前导零也能命中
    assert len(df) == 1


def test_cli_passes_filter_to_strategy(monkeypatch):
    """--filter 参数透传给 MACrossStrategy"""
    prices = [100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    df = pd.DataFrame({"date": dates, "open": prices, "high": prices,
                       "low": prices, "close": prices, "volume": [1000.0] * 10})
    monkeypatch.setattr(run_module, "load_kline", lambda code, db_path=None: df)

    captured = {}
    real_cls = run_module.MACrossStrategy

    def spy(short_period, long_period, filter_period=0, filter_exit=False):
        captured["filter_period"] = filter_period
        return real_cls(short_period, long_period, filter_period, filter_exit)

    monkeypatch.setattr(run_module, "MACrossStrategy", spy)
    monkeypatch.setattr(sys, "argv", ["run", "--code", "00700", "--filter", "30"])
    run_module.main()
    assert captured["filter_period"] == 30


def test_cli_passes_filter_exit_to_strategy(monkeypatch):
    """--filter-exit 参数透传给 MACrossStrategy"""
    prices = [100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    df = pd.DataFrame({"date": dates, "open": prices, "high": prices,
                       "low": prices, "close": prices, "volume": [1000.0] * 10})
    monkeypatch.setattr(run_module, "load_kline", lambda code, db_path=None: df)

    captured = {}
    real_cls = run_module.MACrossStrategy

    def spy(short_period, long_period, filter_period=0, filter_exit=False):
        captured["filter_exit"] = filter_exit
        return real_cls(short_period, long_period, filter_period, filter_exit)

    monkeypatch.setattr(run_module, "MACrossStrategy", spy)
    monkeypatch.setattr(sys, "argv", ["run", "--code", "00700", "--filter", "200", "--filter-exit"])
    run_module.main()
    assert captured["filter_exit"] is True
