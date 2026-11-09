"""SQLite K 线存储层

与 scripts/download_kline.py（写入）、backtest/run.py（读取）配合使用。
所有价格数据均为前复权（qfq），qfq 基准会随分红除权漂移，
历史段更新请用 replace_klines 整段替换，不要跨时间增量拼接。
"""
import sqlite3
from datetime import datetime
from pathlib import Path
import json

import pandas as pd

from config import DB_PATH

_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


def _norm(code) -> str:
    """股票代码统一为 5 位（'700' → '00700'）"""
    return str(code).zfill(5)


def init_db(db_path: Path = DB_PATH):
    """建表（幂等）"""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kline (
                code TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL, close REAL, high REAL, low REAL, volume REAL,
                updated_at TEXT,
                PRIMARY KEY (code, date)
            )
        """)


def _dedupe(bars: list[dict]) -> list[dict]:
    """同日期去重，后写覆盖先写"""
    by_date = {}
    for b in bars:
        by_date[b["date"]] = b
    return list(by_date.values())


def replace_klines(code: str, bars: list[dict], db_path: Path = DB_PATH) -> int:
    """整段替换该股票的 K 线（先清后写），返回写入条数"""
    code = _norm(code)
    init_db(db_path)
    rows = _dedupe(bars)
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM kline WHERE code = ?", (code,))
        conn.executemany(
            "INSERT INTO kline (code, date, open, close, high, low, volume, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(code, b["date"], b["open"], b["close"], b["high"], b["low"], b["volume"], now)
             for b in rows],
        )
    return len(rows)


def upsert_klines(code: str, bars: list[dict], db_path: Path = DB_PATH) -> int:
    """增量写入：只把库中没有的新日期计入返回值，重叠日期顺带覆盖，历史不删。

    ⚠️ qfq 基准会随分红除权漂移，跨时间拼接的新旧 K 线可能基准不一致，
    定期用 replace_klines 整段重拉校正（见 README「数据更新」）。

    Returns:
        新增（此前不存在的日期）条数
    """
    code = _norm(code)
    init_db(db_path)
    rows = _dedupe(bars)
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        existing = {r[0] for r in conn.execute("SELECT date FROM kline WHERE code = ?", (code,))}
        conn.executemany(
            "INSERT OR REPLACE INTO kline (code, date, open, close, high, low, volume, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(code, b["date"], b["open"], b["close"], b["high"], b["low"], b["volume"], now)
             for b in rows],
        )
    return sum(1 for b in rows if b["date"] not in existing)


def import_json(code: str, json_path: Path, db_path: Path = DB_PATH) -> int:
    """导入共享格式 JSON（{updatedAt, data[]}，与热力图项目兼容）。

    用 upsert 合并语义（不覆盖库中更长的历史），返回新增条数。
    """
    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return upsert_klines(code, payload.get("data", []), db_path)


def load_klines(code: str, db_path: Path = DB_PATH) -> pd.DataFrame:
    """读取该股票全部 K 线，按日期升序"""
    code = _norm(code)
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM kline"
            " WHERE code = ? ORDER BY date",
            conn, params=(code,),
        )
    return df


def list_codes(db_path: Path = DB_PATH) -> list[str]:
    """列出库中全部股票代码（升序）"""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT code FROM kline ORDER BY code").fetchall()
    return [r[0] for r in rows]


def delete_klines(code: str, db_path: Path = DB_PATH):
    """删除该股票全部 K 线"""
    code = _norm(code)
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM kline WHERE code = ?", (code,))
