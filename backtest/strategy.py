"""交易策略定义"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from .indicators import calc_ma


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


class MACrossStrategy(Strategy):
    """MA 金叉策略
    - MA 短周期上穿 MA 长周期 → 买入
    - MA 短周期下穿 MA 长周期 → 卖出
    """

    def __init__(self, short_period: int = 5, long_period: int = 20):
        self.short_period = short_period
        self.long_period = long_period

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        df = df.copy()
        df["ma_short"] = calc_ma(df["close"], self.short_period)
        df["ma_long"] = calc_ma(df["close"], self.long_period)

        signals = pd.Series(Signal.HOLD, index=df.index)

        for i in range(1, len(df)):
            prev_short = df["ma_short"].iloc[i - 1]
            prev_long = df["ma_long"].iloc[i - 1]
            curr_short = df["ma_short"].iloc[i]
            curr_long = df["ma_long"].iloc[i]

            if pd.isna(prev_short) or pd.isna(prev_long):
                continue

            # 金叉：短均线从下往上穿越长均线
            if prev_short <= prev_long and curr_short > curr_long:
                signals.iloc[i] = Signal.BUY
            # 死叉：短均线从上往下穿越长均线
            elif prev_short >= prev_long and curr_short < curr_long:
                signals.iloc[i] = Signal.SELL

        return signals
