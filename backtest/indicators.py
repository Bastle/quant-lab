"""技术指标计算"""
import pandas as pd


def calc_ma(close: pd.Series, period: int) -> pd.Series:
    """计算移动平均线"""
    return close.rolling(window=period).mean()


def calc_ema(close: pd.Series, period: int) -> pd.Series:
    """计算指数移动平均线"""
    return close.ewm(span=period, adjust=False).mean()


def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """计算 MACD 指标"""
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = (dif - dea) * 2
    return dif, dea, macd


def calc_volume_ratio(volume: pd.Series, period: int = 5) -> pd.Series:
    """量比 = 当日成交量 / 前 N 日平均成交量（基准不含当日，避免巨量日失真）"""
    return volume / volume.rolling(window=period).mean().shift(1)


def calc_volume_percentile(volume: pd.Series, window: int = 250, q: float = 0.95) -> pd.Series:
    """成交量分位基准 = 前 window 日成交量的 q 分位（不含当日）"""
    return volume.rolling(window=window).quantile(q).shift(1)


def calc_trend_template(close: pd.Series) -> pd.DataFrame:
    """趋势模板（Minervini 变体）7 条件布尔表，买入需全部满足

    1. close > MA150 且 close > MA200        above_150_200
    2. MA150 > MA200                          ma150_gt_ma200
    3. MA200 高于 20 个交易日前（上涨≥1个月）  ma200_rising
    4. MA50 > MA150 且 MA50 > MA200           ma50_above
    5. close ≥ 52 周(250日)最低 × 1.25        off_low
    6. close ≥ 52 周(250日)最高 × 0.75        near_high
    7. close > MA50                           above_ma50

    全部基于收盘价、只用当日及以前数据；窗口/均线历史不足无法判定的条件按 False 处理。
    """
    ma50 = calc_ma(close, 50)
    ma150 = calc_ma(close, 150)
    ma200 = calc_ma(close, 200)
    lo52 = close.rolling(window=250).min()
    hi52 = close.rolling(window=250).max()
    return pd.DataFrame({
        "above_150_200": (close > ma150) & (close > ma200),
        "ma150_gt_ma200": ma150 > ma200,
        "ma200_rising": ma200 > ma200.shift(20),
        "ma50_above": (ma50 > ma150) & (ma50 > ma200),
        "off_low": close >= lo52 * 1.25,
        "near_high": close >= hi52 * 0.75,
        "above_ma50": close > ma50,
    })
