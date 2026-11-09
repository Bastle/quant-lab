"""SQLite 存储层测试"""
import json

import storage


def bar(date: str, close: float = 100.0) -> dict:
    """构造一根 K 线"""
    return {
        "date": date, "open": close - 1.0, "close": close,
        "high": close + 1.0, "low": close - 2.0, "volume": 1000.0,
    }


def test_init_db_idempotent(tmp_path):
    db = tmp_path / "test.db"
    storage.init_db(db)
    storage.init_db(db)  # 幂等，不报错
    assert storage.replace_klines("00700", [bar("2024-01-02")], db) == 1


def test_replace_and_load_roundtrip(tmp_path):
    db = tmp_path / "test.db"
    bars = [bar("2024-01-03", 103.0), bar("2024-01-02", 102.0), bar("2024-01-04", 104.0)]
    assert storage.replace_klines("00700", bars, db) == 3

    df = storage.load_klines("00700", db)
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert list(df["date"]) == ["2024-01-02", "2024-01-03", "2024-01-04"]  # 按日期升序
    assert df["close"].tolist() == [102.0, 103.0, 104.0]
    assert df["open"].tolist() == [101.0, 102.0, 103.0]
    assert df["high"].tolist() == [103.0, 104.0, 105.0]
    assert df["low"].tolist() == [100.0, 101.0, 102.0]
    assert df["volume"].tolist() == [1000.0, 1000.0, 1000.0]


def test_replace_clears_old_data(tmp_path):
    db = tmp_path / "test.db"
    storage.replace_klines("00700", [bar("2024-01-02"), bar("2024-01-03"), bar("2024-01-04")], db)
    assert storage.replace_klines("00700", [bar("2024-02-01", 200.0)], db) == 1

    df = storage.load_klines("00700", db)
    assert list(df["date"]) == ["2024-02-01"]  # 旧数据被清除
    assert df["close"].tolist() == [200.0]


def test_replace_dedupes_same_date_in_batch(tmp_path):
    db = tmp_path / "test.db"
    n = storage.replace_klines("00700", [bar("2024-01-02", 100.0), bar("2024-01-02", 110.0)], db)
    assert n == 1  # 同日期去重

    df = storage.load_klines("00700", db)
    assert len(df) == 1
    assert df["close"].iloc[0] == 110.0  # 后者覆盖前者


def test_load_klines_empty(tmp_path):
    db = tmp_path / "test.db"
    df = storage.load_klines("00700", db)
    assert len(df) == 0
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_list_codes_and_delete_klines(tmp_path):
    db = tmp_path / "test.db"
    storage.replace_klines("00700", [bar("2024-01-02")], db)
    storage.replace_klines("00005", [bar("2024-01-02")], db)
    assert storage.list_codes(db) == ["00005", "00700"]

    storage.delete_klines("00700", db)
    assert storage.list_codes(db) == ["00005"]
    assert len(storage.load_klines("00700", db)) == 0
    assert len(storage.load_klines("00005", db)) == 1  # 其他股票不受影响


def test_upsert_adds_new_dates_only(tmp_path):
    db = tmp_path / "test.db"
    old = [bar("2024-01-02", 102.0), bar("2024-01-03", 103.0), bar("2024-01-04", 104.0)]
    assert storage.upsert_klines("00700", old, db) == 3
    # 同样 3 条再来一次 → 0 条新增，历史不被误删
    assert storage.upsert_klines("00700", old, db) == 0
    # 2 条旧日期 + 1 条新日期 → 只有 1 条新增
    mixed = [bar("2024-01-03", 103.0), bar("2024-01-04", 104.0), bar("2024-01-05", 105.0)]
    assert storage.upsert_klines("00700", mixed, db) == 1

    df = storage.load_klines("00700", db)
    assert list(df["date"]) == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    assert df["close"].iloc[0] == 102.0  # 历史保留


def test_upsert_overwrites_existing_date(tmp_path):
    db = tmp_path / "test.db"
    storage.upsert_klines("00700", [bar("2024-01-02", 100.0)], db)
    assert storage.upsert_klines("00700", [bar("2024-01-02", 110.0)], db) == 0  # 不算新增

    df = storage.load_klines("00700", db)
    assert len(df) == 1
    assert df["close"].iloc[0] == 110.0  # 重叠日期顺带覆盖（吸收盘后修正）


def test_import_json(tmp_path):
    db = tmp_path / "test.db"
    json_path = tmp_path / "00700.json"
    payload = {
        "updatedAt": 1716700000000,
        "data": [
            {"date": "2024-01-02", "open": 295.0, "close": 298.4, "high": 301.2, "low": 293.8, "volume": 12345678},
            {"date": "2024-01-03", "open": 298.0, "close": 300.0, "high": 302.0, "low": 296.0, "volume": 23456789},
        ],
    }
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    assert storage.import_json("00700", json_path, db) == 2
    df = storage.load_klines("00700", db)
    assert list(df["date"]) == ["2024-01-02", "2024-01-03"]
    assert df["close"].tolist() == [298.4, 300.0]
    assert df["volume"].tolist() == [12345678.0, 23456789.0]

    # 重复导入幂等
    assert storage.import_json("00700", json_path, db) == 0
    assert len(storage.load_klines("00700", db)) == 2


def test_code_normalized_to_five_digits(tmp_path):
    """代码统一归一化为 5 位，'700' 与 '00700' 是同一只股票"""
    db = tmp_path / "test.db"
    storage.replace_klines("700", [bar("2024-01-02")], db)  # 不带前导零
    assert storage.list_codes(db) == ["00700"]
    assert len(storage.load_klines("00700", db)) == 1
    assert len(storage.load_klines("700", db)) == 1  # 两种写法命中同一数据
