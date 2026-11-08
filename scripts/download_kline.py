"""历史 K 线数据下载脚本

用法:
    python scripts/download_kline.py --code 00700 --years 5
    python scripts/download_kline.py --code 00700 --count 1000
    python scripts/download_kline.py --list hstech --years 5
    python scripts/download_kline.py --list all --years 5
"""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
import storage
from config import TENCENT_KLINE_URL, KLINE_DIR, DB_PATH, API_RATE_LIMIT_SEC

MAX_BARS_PER_REQUEST = 800   # 腾讯 API 单次请求上限（约 800~1000 根）
MAX_PAGES = 10               # 分页安全阀
UPDATE_WINDOW = 30           # 增量更新窗口（根）
CONSTITUENTS_PATH = Path(__file__).parent.parent / "data" / "index_constituents.json"


def _get_json(url: str, retries: int = 2) -> dict:
    """请求 JSON（限速 + 指数退避重试）"""
    for attempt in range(retries + 1):
        time.sleep(API_RATE_LIMIT_SEC)  # 限速：每次请求前等待
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError):
            if attempt == retries:
                raise
            time.sleep(API_RATE_LIMIT_SEC * (2 ** (attempt + 1)))  # 指数退避


def fetch_bars(code: str, count: int, start: str = "", end: str = "") -> list[dict]:
    """单次请求 K 线数据（day/qfqday 兼容，脏数据过滤）"""
    symbol = f"hk{code.zfill(5)}"
    url = f"{TENCENT_KLINE_URL}?param={symbol},day,{start},{end},{count},qfq"
    print(f"  请求: {url}")
    json_data = _get_json(url)
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


def download_kline(code: str, count: int = 240) -> list[dict]:
    """分页下载并按日期合并去重，返回最近 count 条（按日期升序）"""
    merged: dict[str, dict] = {}
    end = ""
    for _ in range(MAX_PAGES):
        batch = fetch_bars(code, min(MAX_BARS_PER_REQUEST, count - len(merged)), end=end)
        new = [b for b in batch if b["date"] not in merged]
        if not new:
            break  # 历史已取完（或停牌无数据）
        for b in new:
            merged[b["date"]] = b
        if len(merged) >= count:
            break
        # 向更早日期翻页：以当前最早日期 -1 天为右边界
        earliest = min(merged)
        end = (datetime.strptime(earliest, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    bars = sorted(merged.values(), key=lambda b: b["date"])
    return bars[-count:] if len(bars) > count else bars


def write_json_file(code: str, data: list[dict], kline_dir: Path = KLINE_DIR) -> Path:
    """写共享格式 JSON（{updatedAt, data[]}，与热力图项目兼容）"""
    filepath = Path(kline_dir) / f"{code.zfill(5)}.json"
    payload = {"updatedAt": int(datetime.now().timestamp() * 1000), "data": data}
    filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return filepath


def save_kline(code: str, data: list[dict], db_path: Path = DB_PATH,
               kline_dir: Path = KLINE_DIR, write_json: bool = True):
    """保存 K 线：SQLite 必写，JSON 双写（热力图项目共享格式，可用 write_json=False 关闭）"""
    n = storage.replace_klines(code, data, db_path)
    print(f"  保存: SQLite {code.zfill(5)} ({n} 条)")
    if write_json:
        filepath = write_json_file(code, data, kline_dir)
        print(f"  保存: {filepath} ({len(data)} 条)")


def update_code(code: str, count: int | None = None, db_path: Path = DB_PATH,
                kline_dir: Path = KLINE_DIR, write_json: bool = True, full: bool = False) -> dict:
    """更新单只股票（策略 C：增量追加 + 定期全量校正），返回 {code, mode, new_bars}

    - full=True: 整段重拉替换（qfq 漂移校正），条数 = count 或库中现有条数
    - 无存量数据: 自动全量下载
    - 否则: 拉最近 UPDATE_WINDOW 根增量写入（新日期插入，重叠日期顺带覆盖）
    """
    existing = storage.load_klines(code, db_path)
    existing_dates = set(existing["date"]) if not existing.empty else set()

    if full:
        bars = download_kline(code, count or (len(existing) or 240))
        mode = "full"
    elif existing.empty:
        bars = download_kline(code, count or 240)
        mode = "auto-full"
    else:
        bars = download_kline(code, UPDATE_WINDOW)
        mode = "incremental"

    if not bars:
        print("  跳过: 无数据（停牌/退市？）")
        return {"code": code, "mode": "empty", "new_bars": 0}

    if mode == "incremental":
        new_bars = storage.upsert_klines(code, bars, db_path)
        merged = storage.load_klines(code, db_path).to_dict("records")
    else:
        storage.replace_klines(code, bars, db_path)
        new_bars = sum(1 for b in bars if b["date"] not in existing_dates)
        merged = bars

    if write_json:
        write_json_file(code, merged, kline_dir)
    print(f"  {mode}: 新增 {new_bars} 条")
    return {"code": code, "mode": mode, "new_bars": new_bars}


def update_all(count: int | None = None, db_path: Path = DB_PATH,
               kline_dir: Path = KLINE_DIR, write_json: bool = True, full: bool = False) -> dict:
    """增量更新库中全部股票（--full 时全量重拉），返回摘要"""
    codes = storage.list_codes(db_path)
    summary = {"added": 0, "updated": 0, "unchanged": 0, "failed": 0}
    for i, code in enumerate(codes, 1):
        print(f"[{i}/{len(codes)}] {code}")
        try:
            r = update_code(code, count, db_path=db_path, kline_dir=kline_dir,
                            write_json=write_json, full=full)
        except (requests.RequestException, ValueError) as e:
            print(f"  失败: {e}")
            summary["failed"] += 1
            continue
        summary["added"] += r["new_bars"]
        if r["new_bars"] > 0:
            summary["updated"] += 1
        else:
            summary["unchanged"] += 1
    return summary


def batch_codes(list_name: str, constituents_path: Path = CONSTITUENTS_PATH) -> list[str]:
    """按名单取代码：all = 先 hstech 后 hsi，重叠去重"""
    payload = json.loads(Path(constituents_path).read_text(encoding="utf-8"))
    if list_name == "hstech":
        items = payload["hstech"]
    elif list_name == "hsi":
        items = payload["hsi"]
    elif list_name == "all":
        items = payload["hstech"] + payload["hsi"]
    else:
        raise ValueError(f"未知名单: {list_name}")
    codes = []
    for it in items:
        code = str(it["code"]).zfill(5)
        if code not in codes:
            codes.append(code)
    return codes


def download_list(list_name: str, count: int, db_path: Path = DB_PATH,
                  kline_dir: Path = KLINE_DIR, write_json: bool = True,
                  constituents_path: Path = CONSTITUENTS_PATH) -> dict:
    """按名单批量下载，返回摘要 {success, skipped, failed}"""
    codes = batch_codes(list_name, constituents_path)
    summary = {"success": 0, "skipped": 0, "failed": 0}
    for i, code in enumerate(codes, 1):
        print(f"[{i}/{len(codes)}] {code}")
        try:
            data = download_kline(code, count)
        except (requests.RequestException, ValueError) as e:
            print(f"  失败: {e}")
            summary["failed"] += 1
            continue
        if not data:
            print("  跳过: 无数据（停牌/退市？）")
            summary["skipped"] += 1
            continue
        save_kline(code, data, db_path=db_path, kline_dir=kline_dir, write_json=write_json)
        summary["success"] += 1
    return summary


def main():
    parser = argparse.ArgumentParser(description="下载/更新历史 K 线数据")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--code", help="单只更新（无存量数据时自动全量下载；配合 --full 整段重拉）")
    group.add_argument("--list", dest="list_name", choices=["hstech", "hsi", "all"],
                       help="按成分股名单批量下载")
    group.add_argument("--update-all", action="store_true", help="增量更新库中全部股票")
    parser.add_argument("--count", type=int, help="请求条数（默认 240；--full 默认沿用库中条数）")
    parser.add_argument("--years", type=int, help="按年数换算条数（约 250 条/年）")
    parser.add_argument("--full", action="store_true",
                        help="整段重拉替换（定期全量校正，消除前复权漂移）")
    parser.add_argument("--no-json", action="store_true", help="不写 JSON 双写文件")
    args = parser.parse_args()
    count = args.years * 250 if args.years else args.count

    if args.update_all:
        print("全量重拉库中全部股票..." if args.full else "增量更新库中全部股票...")
        summary = update_all(count, write_json=not args.no_json, full=args.full)
        print(f"完成！新增 {summary['added']} 条 / 更新 {summary['updated']} 只"
              f" / 无新数据 {summary['unchanged']} 只 / 失败 {summary['failed']} 只")
    elif args.list_name:
        print(f"批量下载名单 {args.list_name}，每只 {count or 240} 条...")
        summary = download_list(args.list_name, count or 240, write_json=not args.no_json)
        print(f"完成！成功 {summary['success']} / 跳过 {summary['skipped']} / 失败 {summary['failed']}")
    else:
        print(f"更新 {args.code} K 线{'（全量重拉）' if args.full else '（增量）'}...")
        r = update_code(args.code, count, write_json=not args.no_json, full=args.full)
        print(f"完成！模式 {r['mode']}，新增 {r['new_bars']} 条")


if __name__ == "__main__":
    main()
