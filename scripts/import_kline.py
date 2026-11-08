"""批量导入共享格式 JSON 到 SQLite（把热力图项目存量数据做种子）

用法:
    python scripts/import_kline.py --dir ../hongkong-etf/data/kline
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import storage
from config import DB_PATH, KLINE_DIR


def import_dir(json_dir: Path, db_path: Path = DB_PATH) -> dict:
    """把目录下所有 {code}.json 导入 SQLite，返回 {code: 新增条数}"""
    summary = {}
    for filepath in sorted(Path(json_dir).glob("*.json")):
        code = filepath.stem
        n = storage.import_json(code, filepath, db_path)
        summary[code] = n
        print(f"  {code}: 新增 {n} 条")
    return summary


def main():
    parser = argparse.ArgumentParser(description="批量导入 K 线 JSON 到 SQLite")
    parser.add_argument("--dir", default=str(KLINE_DIR), help="JSON 目录（默认 data/kline）")
    parser.add_argument("--db", default=str(DB_PATH), help="数据库路径（默认 data/quant.db）")
    args = parser.parse_args()
    summary = import_dir(args.dir, db_path=Path(args.db))
    print(f"完成！共 {len(summary)} 只股票，新增 {sum(summary.values())} 条")


if __name__ == "__main__":
    main()
