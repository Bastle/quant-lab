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

    def spy(short_period, long_period, filter_period=0, filter_exit=False, vol_ratio=0.0,
            volume_exit=False, trailing_stop=0.0, trend_template=False):
        captured["filter_period"] = filter_period
        return real_cls(short_period, long_period, filter_period, filter_exit, vol_ratio,
                        volume_exit, trailing_stop, trend_template)

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

    def spy(short_period, long_period, filter_period=0, filter_exit=False, vol_ratio=0.0,
            volume_exit=False, trailing_stop=0.0, trend_template=False):
        captured["filter_exit"] = filter_exit
        return real_cls(short_period, long_period, filter_period, filter_exit, vol_ratio,
                        volume_exit, trailing_stop, trend_template)

    monkeypatch.setattr(run_module, "MACrossStrategy", spy)
    monkeypatch.setattr(sys, "argv", ["run", "--code", "00700", "--filter", "200", "--filter-exit"])
    run_module.main()
    assert captured["filter_exit"] is True


def test_cli_price_ma_strategy(monkeypatch):
    """--strategy price_ma --ma 60 构造 PriceMACrossStrategy 并透传周期"""
    prices = [100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    df = pd.DataFrame({"date": dates, "open": prices, "high": prices,
                       "low": prices, "close": prices, "volume": [1000.0] * 10})
    monkeypatch.setattr(run_module, "load_kline", lambda code, db_path=None: df)

    captured = {}
    real_cls = run_module.PriceMACrossStrategy

    def spy(period=200, vol_ratio=0.0, volume_exit=False, trailing_stop=0.0,
            trend_template=False):
        captured["period"] = period
        return real_cls(period, vol_ratio, volume_exit, trailing_stop, trend_template)

    monkeypatch.setattr(run_module, "PriceMACrossStrategy", spy)
    monkeypatch.setattr(sys, "argv",
                        ["run", "--code", "00700", "--strategy", "price_ma", "--ma", "60"])
    run_module.main()
    assert captured["period"] == 60


def test_cli_passes_vol_ratio_to_strategies(monkeypatch):
    """--vol-ratio 透传给两个策略"""
    prices = [100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    df = pd.DataFrame({"date": dates, "open": prices, "high": prices,
                       "low": prices, "close": prices, "volume": [1000.0] * 10})
    monkeypatch.setattr(run_module, "load_kline", lambda code, db_path=None: df)

    captured = {}
    real_ma = run_module.MACrossStrategy
    real_px = run_module.PriceMACrossStrategy

    def spy_ma(short_period, long_period, filter_period=0, filter_exit=False, vol_ratio=0.0,
               volume_exit=False, trailing_stop=0.0, trend_template=False):
        captured["ma_vol"] = vol_ratio
        return real_ma(short_period, long_period, filter_period, filter_exit, vol_ratio,
                       volume_exit, trailing_stop, trend_template)

    def spy_px(period=200, vol_ratio=0.0, volume_exit=False, trailing_stop=0.0,
               trend_template=False):
        captured["px_vol"] = vol_ratio
        return real_px(period, vol_ratio, volume_exit, trailing_stop, trend_template)

    monkeypatch.setattr(run_module, "MACrossStrategy", spy_ma)
    monkeypatch.setattr(run_module, "PriceMACrossStrategy", spy_px)

    monkeypatch.setattr(sys, "argv", ["run", "--code", "00700", "--vol-ratio", "1.5"])
    run_module.main()
    assert captured["ma_vol"] == 1.5

    monkeypatch.setattr(sys, "argv",
                        ["run", "--code", "00700", "--strategy", "price_ma", "--vol-ratio", "2"])
    run_module.main()
    assert captured["px_vol"] == 2.0


def test_cli_passes_volume_exit_to_strategies(monkeypatch):
    """--volume-exit 透传给两个策略"""
    prices = [100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    df = pd.DataFrame({"date": dates, "open": prices, "high": prices,
                       "low": prices, "close": prices, "volume": [1000.0] * 10})
    monkeypatch.setattr(run_module, "load_kline", lambda code, db_path=None: df)

    captured = {}
    real_ma = run_module.MACrossStrategy
    real_px = run_module.PriceMACrossStrategy

    def spy_ma(short_period, long_period, filter_period=0, filter_exit=False, vol_ratio=0.0,
               volume_exit=False, trailing_stop=0.0, trend_template=False):
        captured["ma_exit"] = volume_exit
        return real_ma(short_period, long_period, filter_period, filter_exit, vol_ratio,
                       volume_exit, trailing_stop, trend_template)

    def spy_px(period=200, vol_ratio=0.0, volume_exit=False, trailing_stop=0.0,
               trend_template=False):
        captured["px_exit"] = volume_exit
        return real_px(period, vol_ratio, volume_exit, trailing_stop, trend_template)

    monkeypatch.setattr(run_module, "MACrossStrategy", spy_ma)
    monkeypatch.setattr(run_module, "PriceMACrossStrategy", spy_px)

    monkeypatch.setattr(sys, "argv", ["run", "--code", "00700", "--volume-exit"])
    run_module.main()
    assert captured["ma_exit"] is True

    monkeypatch.setattr(sys, "argv",
                        ["run", "--code", "00700", "--strategy", "price_ma", "--volume-exit"])
    run_module.main()
    assert captured["px_exit"] is True


def test_cli_passes_trailing_stop_to_strategies(monkeypatch):
    """--trailing-stop 透传给两个策略"""
    prices = [100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    df = pd.DataFrame({"date": dates, "open": prices, "high": prices,
                       "low": prices, "close": prices, "volume": [1000.0] * 10})
    monkeypatch.setattr(run_module, "load_kline", lambda code, db_path=None: df)

    captured = {}
    real_ma = run_module.MACrossStrategy
    real_px = run_module.PriceMACrossStrategy

    def spy_ma(short_period, long_period, filter_period=0, filter_exit=False, vol_ratio=0.0,
               volume_exit=False, trailing_stop=0.0, trend_template=False):
        captured["ma_stop"] = trailing_stop
        return real_ma(short_period, long_period, filter_period, filter_exit, vol_ratio,
                       volume_exit, trailing_stop, trend_template)

    def spy_px(period=200, vol_ratio=0.0, volume_exit=False, trailing_stop=0.0,
               trend_template=False):
        captured["px_stop"] = trailing_stop
        return real_px(period, vol_ratio, volume_exit, trailing_stop, trend_template)

    monkeypatch.setattr(run_module, "MACrossStrategy", spy_ma)
    monkeypatch.setattr(run_module, "PriceMACrossStrategy", spy_px)

    monkeypatch.setattr(sys, "argv", ["run", "--code", "00700", "--trailing-stop", "8"])
    run_module.main()
    assert captured["ma_stop"] == 0.08  # CLI 百分数 → 构造器小数

    monkeypatch.setattr(sys, "argv",
                        ["run", "--code", "00700", "--strategy", "price_ma",
                         "--trailing-stop", "12"])
    run_module.main()
    assert captured["px_stop"] == 0.12


def test_cli_passes_trend_template_to_strategies(monkeypatch):
    """--trend-template 透传给两个策略"""
    prices = [100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    df = pd.DataFrame({"date": dates, "open": prices, "high": prices,
                       "low": prices, "close": prices, "volume": [1000.0] * 10})
    monkeypatch.setattr(run_module, "load_kline", lambda code, db_path=None: df)

    captured = {}
    real_ma = run_module.MACrossStrategy
    real_px = run_module.PriceMACrossStrategy

    def spy_ma(short_period, long_period, filter_period=0, filter_exit=False, vol_ratio=0.0,
               volume_exit=False, trailing_stop=0.0, trend_template=False):
        captured["ma_tpl"] = trend_template
        return real_ma(short_period, long_period, filter_period, filter_exit, vol_ratio,
                       volume_exit, trailing_stop, trend_template)

    def spy_px(period=200, vol_ratio=0.0, volume_exit=False, trailing_stop=0.0,
               trend_template=False):
        captured["px_tpl"] = trend_template
        return real_px(period, vol_ratio, volume_exit, trailing_stop, trend_template)

    monkeypatch.setattr(run_module, "MACrossStrategy", spy_ma)
    monkeypatch.setattr(run_module, "PriceMACrossStrategy", spy_px)

    monkeypatch.setattr(sys, "argv", ["run", "--code", "00700", "--trend-template"])
    run_module.main()
    assert captured["ma_tpl"] is True

    monkeypatch.setattr(sys, "argv",
                        ["run", "--code", "00700", "--strategy", "price_ma", "--trend-template"])
    run_module.main()
    assert captured["px_tpl"] is True


def test_cli_template_strategy(monkeypatch):
    """--strategy template 构造 TrendTemplateStrategy 并透传参数"""
    prices = [100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    df = pd.DataFrame({"date": dates, "open": prices, "high": prices,
                       "low": prices, "close": prices, "volume": [1000.0] * 10})
    monkeypatch.setattr(run_module, "load_kline", lambda code, db_path=None: df)

    captured = {}
    real_cls = run_module.TrendTemplateStrategy

    def spy(period=200, volume_exit=False, trailing_stop=0.0):
        captured["period"] = period
        captured["volume_exit"] = volume_exit
        captured["trailing_stop"] = trailing_stop
        return real_cls(period, volume_exit, trailing_stop)

    monkeypatch.setattr(run_module, "TrendTemplateStrategy", spy)
    monkeypatch.setattr(sys, "argv",
                        ["run", "--code", "00700", "--strategy", "template", "--ma", "60",
                         "--volume-exit", "--trailing-stop", "8"])
    run_module.main()
    assert captured["period"] == 60
    assert captured["volume_exit"] is True
    assert captured["trailing_stop"] == 0.08  # CLI 百分数 → 构造器小数
