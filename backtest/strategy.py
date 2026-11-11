"""交易策略定义"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from .indicators import calc_ma, calc_trend_template, calc_volume_percentile, calc_volume_ratio


class Signal(Enum):
    """交易信号"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class TradeRecord:
    """交易记录"""
    date: str
    signal: Signal
    price: float
    shares: int
    commission: float
    stamp_tax: float
    slippage: float


class Strategy(ABC):
    """策略基类"""

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """生成交易信号序列"""
        ...


def _apply_trailing_stop(df: pd.DataFrame, signals: pd.Series, pct: float) -> pd.Series:
    """移动止损（吊灯式）：持仓期收盘价从最高收盘价回撤触及 pct → 当日卖出

    优先级最高（覆盖买入及其他卖出）；止损后清仓，下一个买入信号正常入场，
    新仓的止损基准从新买入价重新跟踪。
    """
    out = signals.copy()
    holding = False
    peak = 0.0
    for i in range(len(df)):
        close = df["close"].iloc[i]
        if holding:
            peak = max(peak, close)
            if close <= peak * (1 - pct):
                out.iloc[i] = Signal.SELL
                holding = False
            elif out.iloc[i] == Signal.SELL:
                holding = False
        elif out.iloc[i] == Signal.BUY:
            holding = True
            peak = close
    return out


def _apply_volume_exit(df: pd.DataFrame, signals: pd.Series) -> pd.Series:
    """巨量出货卖出（B+V1）：连续 3 日成交量 ≥ 前 250 日 95 分位 且 3 日累计下跌 → 当日卖出

    优先级最高（覆盖买入及其他卖出）。
    """
    big = (df["volume"] >= calc_volume_percentile(df["volume"])).fillna(False)
    exit_sig = (big.rolling(3).sum() == 3) & (df["close"] < df["close"].shift(3))
    out = signals.copy()
    out[exit_sig.fillna(False)] = Signal.SELL
    return out


class MACrossStrategy(Strategy):
    """MA 金叉策略
    - MA 短周期上穿 MA 长周期 → 买入
    - MA 短周期下穿 MA 长周期 → 卖出
    - filter_period > 0 时启用趋势过滤：金叉当日收盘价须在 MA(filter_period) 上方
      才买入（只禁止开新仓，卖出不受过滤影响）
    - filter_exit=True 时更进一步：收盘价跌破 MA(filter_period) 当天强制卖出（清仓）
    - vol_ratio > 0 时启用放量确认：金叉当日量比须达阈值才买入（只禁止开新仓）
    - volume_exit=True 时启用巨量出货卖出（替换死叉卖出）：连续 3 日成交量 ≥ 前 250 日
      95 分位 且 3 日累计下跌 → 第 3 日收盘卖出
    - trailing_stop > 0 时启用移动止损：持仓期收盘价从最高收盘价回撤超过该比例 → 卖出
    - trend_template=True 时启用趋势模板买入过滤（Minervini 7 条件全满足才买）
    """

    def __init__(self, short_period: int = 5, long_period: int = 20,
                 filter_period: int = 0, filter_exit: bool = False, vol_ratio: float = 0.0,
                 volume_exit: bool = False, trailing_stop: float = 0.0,
                 trend_template: bool = False):
        self.short_period = short_period
        self.long_period = long_period
        self.filter_period = filter_period
        self.filter_exit = filter_exit
        self.vol_ratio = vol_ratio
        self.volume_exit = volume_exit
        self.trailing_stop = trailing_stop
        self.trend_template = trend_template

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        df = df.copy()
        df["ma_short"] = calc_ma(df["close"], self.short_period)
        df["ma_long"] = calc_ma(df["close"], self.long_period)
        if self.filter_period > 0:
            df["ma_filter"] = calc_ma(df["close"], self.filter_period)
        if self.vol_ratio > 0:
            df["vol_ratio"] = calc_volume_ratio(df["volume"])
        if self.trend_template:
            tpl_ok = calc_trend_template(df["close"]).all(axis=1)

        signals = pd.Series(Signal.HOLD, index=df.index)

        for i in range(1, len(df)):
            prev_short = df["ma_short"].iloc[i - 1]
            prev_long = df["ma_long"].iloc[i - 1]
            curr_short = df["ma_short"].iloc[i]
            curr_long = df["ma_long"].iloc[i]

            if pd.isna(prev_short) or pd.isna(prev_long):
                continue

            # 趋势过滤：收盘价在过滤均线下方时金叉作废（均线历史不足时不拦截）
            below_filter = False
            if self.filter_period > 0:
                ma_filter = df["ma_filter"].iloc[i]
                below_filter = not pd.isna(ma_filter) and df["close"].iloc[i] <= ma_filter

            # 金叉：短均线从下往上穿越长均线
            if prev_short <= prev_long and curr_short > curr_long:
                buy_ok = not below_filter
                # 趋势模板：7 条件任一不满足/无法判定 → 不买
                if buy_ok and self.trend_template:
                    buy_ok = bool(tpl_ok.iloc[i])
                # 放量确认：量比低于阈值的金叉作废（量比历史不足时不拦截）
                if buy_ok and self.vol_ratio > 0:
                    vr = df["vol_ratio"].iloc[i]
                    buy_ok = pd.isna(vr) or vr >= self.vol_ratio
                if buy_ok:
                    signals.iloc[i] = Signal.BUY
            # 死叉：短均线从上往下穿越长均线（巨量出货卖出启用时由其接管）
            elif not self.volume_exit and prev_short >= prev_long and curr_short < curr_long:
                signals.iloc[i] = Signal.SELL

            # 强制清仓：跌破过滤均线当天发卖出（优先级最高，覆盖金叉日）
            if below_filter and self.filter_exit:
                signals.iloc[i] = Signal.SELL

        # 巨量出货：连续 3 日巨量且累计下跌 → 卖出（优先级最高，覆盖买入及其他卖出）
        if self.volume_exit:
            signals = _apply_volume_exit(df, signals)
        if self.trailing_stop > 0:
            signals = _apply_trailing_stop(df, signals, self.trailing_stop)
        return signals


class TrendTemplateStrategy(Strategy):
    """趋势模板策略（Minervini 7 条件即买入规则，不依赖上穿事件）

    - 买入：7 条件由不满足翻转为全部满足的当天；数据不足视为不满足
    - 只在翻转日买入：卖出后须等模板重新经历「不满足→满足」才再入场
    - 卖出：收盘价下穿 MA(period)（volume_exit=True 时由巨量出货替换）
    - trailing_stop > 0 时叠加移动止损（优先级最高）
    - 模板破坏不触发卖出：7 条件只做买入限制
    """

    def __init__(self, period: int = 200, volume_exit: bool = False,
                 trailing_stop: float = 0.0):
        self.period = period
        self.volume_exit = volume_exit
        self.trailing_stop = trailing_stop

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        df = df.copy()
        df["ma"] = calc_ma(df["close"], self.period)
        tpl_ok = calc_trend_template(df["close"]).all(axis=1)
        flip = tpl_ok & ~tpl_ok.shift(1, fill_value=False)

        signals = pd.Series(Signal.HOLD, index=df.index)
        signals[flip] = Signal.BUY

        if self.volume_exit:
            signals = _apply_volume_exit(df, signals)
        else:
            # 下穿卖出：收盘价从上往下穿越 MA(period)
            prev_close = df["close"].shift(1)
            prev_ma = df["ma"].shift(1)
            cross_down = (prev_close >= prev_ma) & (df["close"] < df["ma"])
            signals[cross_down.fillna(False)] = Signal.SELL

        if self.trailing_stop > 0:
            signals = _apply_trailing_stop(df, signals, self.trailing_stop)
        return signals


class PriceMACrossStrategy(Strategy):
    """价格 × 均线策略（单均线趋势跟随）
    - 收盘价上穿 MA(period) → 买入
    - 收盘价下穿 MA(period) → 卖出
    - vol_ratio > 0 时启用放量确认：上穿当日量比须达阈值才买入（只禁止开新仓）
    - volume_exit=True 时启用巨量出货卖出（替换下穿卖出）：连续 3 日成交量 ≥ 前 250 日
      95 分位 且 3 日累计下跌 → 第 3 日收盘卖出
    - trailing_stop > 0 时启用移动止损：持仓期收盘价从最高收盘价回撤超过该比例 → 卖出
    - trend_template=True 时启用趋势模板买入过滤（Minervini 7 条件全满足才买）
    """

    def __init__(self, period: int = 200, vol_ratio: float = 0.0, volume_exit: bool = False,
                 trailing_stop: float = 0.0, trend_template: bool = False):
        self.period = period
        self.vol_ratio = vol_ratio
        self.volume_exit = volume_exit
        self.trailing_stop = trailing_stop
        self.trend_template = trend_template

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        df = df.copy()
        df["ma"] = calc_ma(df["close"], self.period)
        if self.vol_ratio > 0:
            df["vol_ratio"] = calc_volume_ratio(df["volume"])
        if self.trend_template:
            tpl_ok = calc_trend_template(df["close"]).all(axis=1)

        signals = pd.Series(Signal.HOLD, index=df.index)

        for i in range(1, len(df)):
            prev_close = df["close"].iloc[i - 1]
            curr_close = df["close"].iloc[i]
            prev_ma = df["ma"].iloc[i - 1]
            curr_ma = df["ma"].iloc[i]

            if pd.isna(prev_ma) or pd.isna(curr_ma):
                continue  # 均线历史不足，不发信号

            # 上穿：价格从均线下方穿越到上方
            if prev_close <= prev_ma and curr_close > curr_ma:
                buy_ok = True
                # 趋势模板：7 条件任一不满足/无法判定 → 不买
                if buy_ok and self.trend_template:
                    buy_ok = bool(tpl_ok.iloc[i])
                # 放量确认：量比低于阈值的上穿作废（量比历史不足时不拦截）
                if buy_ok and self.vol_ratio > 0:
                    vr = df["vol_ratio"].iloc[i]
                    buy_ok = pd.isna(vr) or vr >= self.vol_ratio
                if buy_ok:
                    signals.iloc[i] = Signal.BUY
            # 下穿：价格从均线上方穿越到下方（巨量出货卖出启用时由其接管）
            elif not self.volume_exit and prev_close >= prev_ma and curr_close < curr_ma:
                signals.iloc[i] = Signal.SELL

        # 巨量出货：连续 3 日巨量且累计下跌 → 卖出（优先级最高，覆盖买入及其他卖出）
        if self.volume_exit:
            signals = _apply_volume_exit(df, signals)
        if self.trailing_stop > 0:
            signals = _apply_trailing_stop(df, signals, self.trailing_stop)
        return signals
