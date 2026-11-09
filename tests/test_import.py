"""JSON 批量导入测试（热力图存量数据 → SQLite 种子）"""
import json

import storage
from scripts import import_kline


def bar(date: str, close: float = 100.0) -> dict:
    return {"date": date, "open": close - 1.0, "close": close,
            "high": close + 1.0, "low": close - 2.0, "volume": 1000.0}


def test_import_dir(tmp_path):
    json_dir = tmp_path / "kline"
    json_dir.mkdir()
    db = tmp_path / "test.db"
    payload = {"updatedAt": 1716700000000,
               "data": [bar("2024-01-02", 102.0), bar("2024-01-03", 103.0)]}
    (json_dir / "00700.json").write_text(json.dumps(payload), encoding="utf-8")
    payload2 = {"updatedAt": 1716700000000, "data": [bar("2024-01-02", 202.0)]}
    (json_dir / "01810.json").write_text(json.dumps(payload2), encoding="utf-8")

    summary = import_kline.import_dir(json_dir, db_path=db)
    assert summary == {"00700": 2, "01810": 1}
    assert storage.list_codes(db) == ["00700", "01810"]
    assert len(storage.load_klines("00700", db)) == 2


def test_import_dir_skips_bad_file(tmp_path):
    json_dir = tmp_path / "kline"
    json_dir.mkdir()
    db = tmp_path / "test.db"
    payload = {"updatedAt": 1716700000000, "data": [bar("2024-01-02", 102.0)]}
    (json_dir / "00700.json").write_text(json.dumps(payload), encoding="utf-8")
    (json_dir / "bad.json").write_text("{ 这不是合法 JSON", encoding="utf-8")

    summary = import_kline.import_dir(json_dir, db_path=db)  # 坏文件跳过，不抛
    assert summary == {"00700": 1}
