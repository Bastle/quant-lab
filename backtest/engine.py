"""回测引擎：买卖撮合、持仓管理、收益计算"""
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .strategy import Strategy, Signal, TradeRecord


@dataclass
class BacktestConfig:
    """回测配置"""
    initial_capital: float = 1_000_000
    commission_rate: float = 0.0003    # 佣金 0.03%
    stamp_tax_rate: float = 0.0013     # 印花税 0.13%（卖出收取）
    slippage_rate: float = 0.001       # 滑点 0.1%


@dataclass
class BacktestResult:
    """回测结果"""
    initial_capital: float = 0
    final_capital: float = 0
    total_return: float = 0            # 总收益率
    annual_return: float = 0           # 年化收益率
    win_rate: float = 0               # 胜率
    max_drawdown: float = 0           # 最大回撤
    sharpe_ratio: float = 0           # 夏普比率
    total_trades: int = 0             # 总交易次数
    trades: list = field(default_factory=list)
    equity_curve: pd.Series = None    # 权益曲线


class BacktestEngine:
    """回测引擎"""

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()

    def run(self, df: pd.DataFrame, strategy: Strategy) -> BacktestResult:
        """执行回测

        Args:
            df: DataFrame，需包含 date, open, high, low, close, volume 列
            strategy: 策略实例

        Returns:
            BacktestResult
        """
        signals = strategy.generate_signals(df)
        capital = self.config.initial_capital
        shares = 0
        trades: list[TradeRecord] = []
        equity_history: list[float] = []

        for i in range(len(df)):
            price = df["close"].iloc[i]
            date = str(df["date"].iloc[i])
            signal = signals.iloc[i]

            if signal == Signal.BUY and shares == 0:
                # 滑点后实际买入价
                buy_price = price * (1 + self.config.slippage_rate)
                # 可买股数（按 100 股整数倍）
                max_shares = int(capital / (buy_price * 100)) * 100
                if max_shares > 0:
                    cost = buy_price * max_shares
                    commission = max(cost * self.config.commission_rate, 5)  # 最低 5 元
                    total_cost = cost + commission

                    if total_cost <= capital:
                        capital -= total_cost
                        shares = max_shares
                        trades.append(TradeRecord(
                            date=date, signal=Signal.BUY, price=buy_price,
                            shares=max_shares, commission=commission,
                            stamp_tax=0, slippage=price * self.config.slippage_rate * max_shares,
                        ))

            elif signal == Signal.SELL and shares > 0:
                # 滑点后实际卖出价
                sell_price = price * (1 - self.config.slippage_rate)
                revenue = sell_price * shares
                commission = max(revenue * self.config.commission_rate, 5)
                stamp_tax = revenue * self.config.stamp_tax_rate
                capital += revenue - commission - stamp_tax

                trades.append(TradeRecord(
                    date=date, signal=Signal.SELL, price=sell_price,
                    shares=shares, commission=commission,
                    stamp_tax=stamp_tax, slippage=price * self.config.slippage_rate * shares,
                ))
                shares = 0

            # 记录每日权益
            equity = capital + shares * price
            equity_history.append(equity)

        # 计算统计指标
        equity_series = pd.Series(equity_history, index=df.index)
        result = self._compute_stats(equity_series, trades)
        return result

    def _compute_stats(self, equity: pd.Series, trades: list[TradeRecord]) -> BacktestResult:
        """计算回测统计指标"""
        initial = self.config.initial_capital
        final = equity.iloc[-1]

        # 总收益率
        total_return = (final - initial) / initial

        # 年化收益率（假设 250 个交易日）
        days = len(equity)
        annual_return = (1 + total_return) ** (250 / max(days, 1)) - 1 if days > 0 else 0

        # 胜率（配对买卖）
        buy_trades = [t for t in trades if t.signal == Signal.BUY]
        sell_trades = [t for t in trades if t.signal == Signal.SELL]
        pair_count = min(len(buy_trades), len(sell_trades))
        win_count = sum(
            1 for i in range(pair_count)
            if sell_trades[i].price > buy_trades[i].price
        )
        win_rate = win_count / pair_count if pair_count > 0 else 0

        # 最大回撤
        cummax = equity.cummax()
        drawdown = (equity - cummax) / cummax
        max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0

        # 夏普比率（简化版，假设无风险利率 3%）
        daily_returns = equity.pct_change().dropna()
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            sharpe = (daily_returns.mean() - 0.03 / 250) / daily_returns.std() * (250 ** 0.5)
        else:
            sharpe = 0

        return BacktestResult(
            initial_capital=initial,
            final_capital=final,
            total_return=total_return,
            annual_return=annual_return,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            total_trades=len(trades),
            trades=trades,
            equity_curve=equity,
        )
