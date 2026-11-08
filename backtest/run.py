"""运行回测

用法:
    python -m backtest.run --code 00700 --strategy ma_cross
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from .engine import BacktestEngine, BacktestConfig
from .strategy import MACrossStrategy
from .report import print_report


def load_kline(code: str) -> pd.DataFrame:
    """从 JSON 文件加载 K 线数据"""
    filepath = Path(__file__).parent.parent / "data" / "kline" / f"{code.zfill(5)}.json"
    if not filepath.exists():
        raise FileNotFoundError(
            f"数据文件不存在: {filepath}\n"
            f"请先运行: python scripts/download_kline.py --code {code}"
        )
    payload = json.loads(filepath.read_text())
    df = pd.DataFrame(payload["data"])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="运行回测")
    parser.add_argument("--code", required=True, help="股票代码，如 00700")
    parser.add_argument("--strategy", default="ma_cross", help="策略名称")
    parser.add_argument("--short", type=int, default=5, help="MA 短周期")
    parser.add_argument("--long", type=int, default=20, help="MA 长周期")
    args = parser.parse_args()

    df = load_kline(args.code)
    print(f"加载 {args.code} K 线: {len(df)} 条 ({df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()})")

    if args.strategy == "ma_cross":
        strategy = MACrossStrategy(short_period=args.short, long_period=args.long)
    else:
        raise ValueError(f"未知策略: {args.strategy}")

    engine = BacktestEngine(BacktestConfig())
    result = engine.run(df, strategy)
    print_report(result, f"MA{args.short}/{args.long} 金叉策略 - {args.code}")


if __name__ == "__main__":
    main()
