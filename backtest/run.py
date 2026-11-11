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
from .strategy import MACrossStrategy
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
    parser.add_argument("--strategy", default="ma_cross", help="策略名称")
    parser.add_argument("--short", type=int, default=5, help="MA 短周期")
    parser.add_argument("--long", type=int, default=20, help="MA 长周期")
    parser.add_argument("--filter", type=int, default=0,
                        help="趋势过滤均线周期（如 200；0=关闭）。金叉须在该均线上方才买入")
    parser.add_argument("--filter-exit", action="store_true",
                        help="跌破过滤均线当天强制清仓（需配合 --filter）")
    args = parser.parse_args()

    df = load_kline(args.code)
    print(f"加载 {args.code} K 线: {len(df)} 条 ({df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()})")

    if args.strategy == "ma_cross":
        strategy = MACrossStrategy(short_period=args.short, long_period=args.long,
                                   filter_period=args.filter, filter_exit=args.filter_exit)
    else:
        raise ValueError(f"未知策略: {args.strategy}")

    engine = BacktestEngine(BacktestConfig())
    result = engine.run(df, strategy)
    title = f"MA{args.short}/{args.long} 金叉策略"
    if args.filter:
        title += f"（MA{args.filter} 趋势过滤"
        title += "+破线清仓）" if args.filter_exit else "）"
    print_report(result, f"{title} - {args.code}")


if __name__ == "__main__":
    main()
