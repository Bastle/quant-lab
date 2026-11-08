"""历史 K 线数据下载脚本

用法:
    python scripts/download_kline.py --code 00700 --years 5
    python scripts/download_kline.py --code 00700 --count 1000
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import TENCENT_KLINE_URL, KLINE_DIR


def download_kline(code: str, count: int = 240) -> list[dict]:
    """从腾讯 API 下载 K 线数据"""
    symbol = f"hk{code.zfill(5)}"
    url = f"{TENCENT_KLINE_URL}?param={symbol},day,,,{count},qfq"
    print(f"  请求: {url}")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    json_data = resp.json()
    day_data = json_data.get("data", {}).get(symbol, {}).get("day") or \
               json_data.get("data", {}).get(symbol, {}).get("qfqday") or []
    klines = []
    for item in day_data:
        try:
            klines.append({
                "date": str(item[0]), "open": float(item[1]), "close": float(item[2]),
                "high": float(item[3]), "low": float(item[4]), "volume": float(item[5]),
            })
        except (IndexError, ValueError):
            continue
    return [k for k in klines if k["open"] > 0 and k["close"] > 0]


def save_kline(code: str, data: list[dict]):
    """保存 K 线数据到 JSON 文件"""
    filepath = KLINE_DIR / f"{code.zfill(5)}.json"
    payload = {"updatedAt": int(datetime.now().timestamp() * 1000), "data": data}
    filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"  保存: {filepath} ({len(data)} 条)")


def main():
    parser = argparse.ArgumentParser(description="下载历史 K 线数据")
    parser.add_argument("--code", required=True, help="股票代码，如 00700")
    parser.add_argument("--count", type=int, default=240, help="请求条数（默认 240）")
    parser.add_argument("--years", type=int, help="按年数换算条数（约 250 条/年）")
    args = parser.parse_args()
    count = args.years * 250 if args.years else args.count
    count = min(count, 1000)
    print(f"下载 {args.code} 历史 K 线，共 {count} 条...")
    data = download_kline(args.code, count)
    if data:
        save_kline(args.code, data)
        print(f"完成！时间范围: {data[0]['date']} ~ {data[-1]['date']}")
    else:
        print("未获取到数据，请检查代码是否正确")


if __name__ == "__main__":
    main()
