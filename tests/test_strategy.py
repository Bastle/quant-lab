"""策略测试（MA 金叉 + 趋势过滤）"""
import pandas as pd

from backtest.indicators import calc_ma
from backtest.strategy import MACrossStrategy, Signal


def make_df(prices: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.DataFrame({
        "date": dates, "open": prices, "close": prices,
        "high": prices, "low": prices, "volume": [1000.0] * len(prices),
    })


# 高位平台 → 暴跌 → 小反弹：唯一金叉（idx 7）出现在 MA5 下方
BELOW_MA = [100, 100, 100, 100, 100, 50, 51, 52, 53, 48, 55]
# 上升趋势回调再涨：唯一金叉（idx 6）出现在 MA5 上方
ABOVE_MA = [50, 51, 52, 53, 48, 55, 56, 57, 58]


def test_filter_blocks_buy_below_ma():
    """金叉发生在过滤均线下方 → 买入信号被拦截"""
    df = make_df(BELOW_MA)
    unfiltered = MACrossStrategy(short_period=2, long_period=3).generate_signals(df)
    assert (unfiltered == Signal.BUY).sum() == 1  # 前提：确实有一次金叉

    filtered = MACrossStrategy(short_period=2, long_period=3, filter_period=5).generate_signals(df)
    assert (filtered == Signal.BUY).sum() == 0  # close < MA5，金叉作废
    assert filtered.iloc[7] == Signal.HOLD


def test_filter_allows_buy_above_ma():
    """金叉发生在过滤均线上方 → 买入信号正常放行（与不过滤一致）"""
    df = make_df(ABOVE_MA)
    unfiltered = MACrossStrategy(short_period=2, long_period=3).generate_signals(df)
    filtered = MACrossStrategy(short_period=2, long_period=3, filter_period=5).generate_signals(df)

    assert (filtered == Signal.BUY).sum() == 1  # 金叉被保留
    assert list(filtered) == list(unfiltered)   # 该数据集下过滤不改变任何信号


def test_filter_zero_disables_filter():
    """filter_period=0（默认）行为与不带过滤的原策略完全一致"""
    df = make_df(BELOW_MA)
    original = MACrossStrategy(short_period=2, long_period=3).generate_signals(df)
    default = MACrossStrategy(short_period=2, long_period=3).generate_signals(df)
    assert list(default) == list(original)
    # 关闭过滤时下方金叉照常买入（说明被拦是过滤的功劳，不是数据没金叉）
    assert default.iloc[7] == Signal.BUY


def test_filter_does_not_force_sell():
    """过滤只禁止开新仓：持仓期间信号不受过滤影响，死叉照常卖出"""
    df = make_df(BELOW_MA)
    filtered = MACrossStrategy(short_period=2, long_period=3, filter_period=5).generate_signals(df)
    # 数据集 1 中 idx 9 有死叉，close(48) < MA5，但卖出信号不受过滤影响
    assert filtered.iloc[9] == Signal.SELL


def test_filter_exit_forces_sell_below_ma():
    """filter_exit=True：收盘价跌破过滤均线当天强制卖出（即使没有死叉）"""
    df = make_df(BELOW_MA)
    base = MACrossStrategy(short_period=2, long_period=3, filter_period=5).generate_signals(df)
    exit_mode = MACrossStrategy(short_period=2, long_period=3, filter_period=5,
                                filter_exit=True).generate_signals(df)

    ma5 = calc_ma(df["close"], 5)
    below = [i for i in range(len(df)) if df["close"].iloc[i] <= ma5.iloc[i]]
    assert below, "前提：数据集中存在跌破 MA5 的交易日"
    # 跌破均线的每一天都发出卖出信号
    assert all(exit_mode.iloc[i] == Signal.SELL for i in below)
    # 而不强制清仓模式下这些日子大多不是卖出（说明信号是 filter_exit 的功劳）
    assert any(base.iloc[i] != Signal.SELL for i in below)


def test_filter_exit_keeps_buy_above_ma():
    """filter_exit=True：均线上方的金叉照常买入（只改卖出行为）"""
    df = make_df(ABOVE_MA)
    exit_mode = MACrossStrategy(short_period=2, long_period=3, filter_period=5,
                                filter_exit=True).generate_signals(df)
    assert (exit_mode == Signal.BUY).sum() == 1  # 均线上方金叉放行


def test_filter_exit_default_off():
    """filter_exit 默认关闭，行为与只禁止开新仓完全一致"""
    df = make_df(BELOW_MA)
    default = MACrossStrategy(short_period=2, long_period=3, filter_period=5).generate_signals(df)
    explicit = MACrossStrategy(short_period=2, long_period=3, filter_period=5,
                               filter_exit=False).generate_signals(df)
    assert list(default) == list(explicit)
