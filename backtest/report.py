"""回测报告生成"""
from .engine import BacktestResult


def print_report(result: BacktestResult, strategy_name: str = ""):
    """打印回测报告"""
    print("=" * 50)
    print(f"  回测报告 {strategy_name}")
    print("=" * 50)
    print(f"  初始资金:    ¥{result.initial_capital:,.0f}")
    print(f"  最终资金:    ¥{result.final_capital:,.0f}")
    print(f"  总收益率:    {result.total_return:+.2%}")
    print(f"  年化收益率:  {result.annual_return:+.2%}")
    print(f"  胜率:        {result.win_rate:.1%}")
    print(f"  最大回撤:    {result.max_drawdown:.2%}")
    print(f"  夏普比率:    {result.sharpe_ratio:.2f}")
    print(f"  总交易次数:  {result.total_trades}")
    print("=" * 50)

    if result.trades:
        print("\n  交易记录（最近 10 笔）:")
        print(f"  {'日期':<12} {'操作':<6} {'价格':>10} {'股数':>8}")
        print("  " + "-" * 40)
        for t in result.trades[-10:]:
            action = "买入" if t.signal.value == "buy" else "卖出"
            print(f"  {t.date:<12} {action:<6} {t.price:>10.2f} {t.shares:>8}")
