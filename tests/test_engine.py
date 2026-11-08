"""回测引擎测试"""
import pandas as pd
import pytest

from backtest.engine import BacktestEngine, BacktestConfig
from backtest.strategy import MACrossStrategy, Signal
from backtest.indicators import calc_ma


def make_test_df() -> pd.DataFrame:
    """构造测试 K 线数据（先跌后涨再跌，保证 MA 金叉和死叉都能出现）"""
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    prices = (
        [130 - i * 0.5 for i in range(30)]   # 下跌 130 → 115.5
        + [115 + i * 0.8 for i in range(40)]  # 上涨 115 → 146.2
        + [146 - i * 0.7 for i in range(30)]  # 下跌 146 → 125.3
    )
    return pd.DataFrame({
        "date": dates,
        "open": prices,
        "close": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "volume": [1000000] * 100,
    })


def test_calc_ma():
    s = pd.Series([1, 2, 3, 4, 5])
    ma3 = calc_ma(s, 3)
    assert pd.isna(ma3.iloc[0])
    assert ma3.iloc[2] == pytest.approx(2.0)
    assert ma3.iloc[4] == pytest.approx(4.0)


def test_ma_cross_signals():
    df = make_test_df()
    strategy = MACrossStrategy(short_period=5, long_period=20)
    signals = strategy.generate_signals(df)
    assert (signals == Signal.BUY).sum() > 0, "应产生买入信号"
    assert (signals == Signal.SELL).sum() > 0, "应产生卖出信号"


def test_backtest_engine():
    df = make_test_df()
    strategy = MACrossStrategy(short_period=5, long_period=20)
    engine = BacktestEngine(BacktestConfig(initial_capital=1000000))
    result = engine.run(df, strategy)
    assert result.initial_capital == 1000000
    assert result.final_capital > 0
    assert result.total_trades > 0
    assert 0 <= result.win_rate <= 1
    assert result.equity_curve is not None
    assert len(result.equity_curve) == len(df)
