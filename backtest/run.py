"""运行回测

用法:
    python -m backtest.run --code 00700 --strategy ma_cross
"""
import argparse
from pathlib import Path

import pandas as pd

import storage
from config import DB_PATH
from .engine import BacktestEngine, BacktestConfig
from .strategy import MACrossStrategy, PriceMACrossStrategy, TrendTemplateStrategy
from .report import print_report


def load_kline(code: str, db_path: Path = DB_PATH) -> pd.DataFrame:
    """从 SQLite 加载 K 线数据"""
    df = storage.load_klines(code, db_path)
    if df.empty:
        raise FileNotFoundError(
            f"数据库中无 {code.zfill(5)} 的 K 线数据\n"
            f"请先运行: python scripts/download_kline.py --code {code} --years 5"
        )
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="运行回测")
    parser.add_argument("--code", required=True, help="股票代码，如 00700")
    parser.add_argument("--strategy", default="ma_cross",
                        choices=["ma_cross", "price_ma", "template"],
                        help="策略名称: ma_cross=MA 金叉, price_ma=价格×均线, template=趋势模板")
    parser.add_argument("--short", type=int, default=5, help="MA 短周期（ma_cross）")
    parser.add_argument("--long", type=int, default=20, help="MA 长周期（ma_cross）")
    parser.add_argument("--ma", type=int, default=200, help="均线周期（price_ma，默认 200）")
    parser.add_argument("--filter", type=int, default=0,
                        help="趋势过滤均线周期（如 200；0=关闭）。金叉须在该均线上方才买入")
    parser.add_argument("--filter-exit", action="store_true",
                        help="跌破过滤均线当天强制清仓（需配合 --filter）")
    parser.add_argument("--vol-ratio", type=float, default=0.0,
                        help="量比放量确认阈值（如 1.5；0=关闭）。买入信号当日量比须达阈值")
    parser.add_argument("--volume-exit", action="store_true",
                        help="巨量出货卖出：连续3日量≥250日95分位且累计下跌→卖出（替换死叉/下穿卖出）")
    parser.add_argument("--trailing-stop", type=float, default=0.0,
                        help="移动止损百分比（如 8；0=关闭）。持仓期收盘价从最高收盘价回撤超过该比例→卖出")
    parser.add_argument("--trend-template", action="store_true",
                        help="趋势模板买入过滤（Minervini 7 条件全满足才买，数据不足不买）")
    args = parser.parse_args()

    df = load_kline(args.code)
    print(f"加载 {args.code} K 线: {len(df)} 条 ({df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()})")

    if args.strategy == "ma_cross":
        strategy = MACrossStrategy(short_period=args.short, long_period=args.long,
                                   filter_period=args.filter, filter_exit=args.filter_exit,
                                   vol_ratio=args.vol_ratio, volume_exit=args.volume_exit,
                                   trailing_stop=args.trailing_stop / 100,
                                   trend_template=args.trend_template)
        title = f"MA{args.short}/{args.long} 金叉策略"
        if args.filter:
            title += f"（MA{args.filter} 趋势过滤"
            title += "+破线清仓）" if args.filter_exit else "）"
    elif args.strategy == "price_ma":
        strategy = PriceMACrossStrategy(period=args.ma, vol_ratio=args.vol_ratio,
                                        volume_exit=args.volume_exit,
                                        trailing_stop=args.trailing_stop / 100,
                                        trend_template=args.trend_template)
        title = f"价格×MA{args.ma} 趋势策略"
    else:  # template
        strategy = TrendTemplateStrategy(period=args.ma, volume_exit=args.volume_exit,
                                         trailing_stop=args.trailing_stop / 100)
        title = f"趋势模板策略（MA{args.ma} 下穿卖出）"
    if args.vol_ratio and args.strategy != "template":
        title += f"（量比≥{args.vol_ratio:g}）"
    if args.volume_exit:
        title += "（巨量出货卖出）"
    if args.trailing_stop:
        title += f"（移动止损{args.trailing_stop:g}%）"
    if args.trend_template and args.strategy != "template":
        title += "（趋势模板）"

    engine = BacktestEngine(BacktestConfig())
    result = engine.run(df, strategy)
    print_report(result, f"{title} - {args.code}")


if __name__ == "__main__":
    main()
