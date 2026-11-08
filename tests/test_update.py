"""K 线更新模式测试（策略 C：增量追加 + 定期全量校正）"""
import json

import pytest

import storage
from scripts import download_kline


def bar(date: str, close: float = 100.0) -> dict:
    return {"date": date, "open": close - 1.0, "close": close,
            "high": close + 1.0, "low": close - 2.0, "volume": 1000.0}


def make_env(tmp_path):
    db = tmp_path / "test.db"
    kline_dir = tmp_path / "kline"
    kline_dir.mkdir()
    return db, kline_dir


def test_update_code_incremental_adds_only_new(tmp_path, monkeypatch):
    db, kline_dir = make_env(tmp_path)
    storage.replace_klines("00700", [bar("2024-01-02", 102.0), bar("2024-01-03", 103.0)], db)
    # 拉回来的窗口含旧日期 + 新日期
    monkeypatch.setattr(download_kline, "download_kline",
                        lambda code, count: [bar("2024-01-03", 103.0), bar("2024-01-04", 104.0)])

    r = download_kline.update_code("00700", db_path=db, kline_dir=kline_dir)
    assert r == {"code": "00700", "mode": "incremental", "new_bars": 1}

    df = storage.load_klines("00700", db)
    assert list(df["date"]) == ["2024-01-02", "2024-01-03", "2024-01-04"]  # 旧数据不被误删
    # JSON 双写为合并后全量
    payload = json.loads((kline_dir / "00700.json").read_text(encoding="utf-8"))
    assert [d["date"] for d in payload["data"]] == ["2024-01-02", "2024-01-03", "2024-01-04"]


def test_update_code_idempotent(tmp_path, monkeypatch):
    db, kline_dir = make_env(tmp_path)
    storage.replace_klines("00700", [bar("2024-01-02", 102.0)], db)
    monkeypatch.setattr(download_kline, "download_kline",
                        lambda code, count: [bar("2024-01-02", 102.0), bar("2024-01-03", 103.0)])

    r1 = download_kline.update_code("00700", db_path=db, kline_dir=kline_dir)
    r2 = download_kline.update_code("00700", db_path=db, kline_dir=kline_dir)
    assert r1["new_bars"] == 1
    assert r2["new_bars"] == 0  # 第二次 0 新增（幂等）


def test_update_code_suspended_skip(tmp_path, monkeypatch):
    db, kline_dir = make_env(tmp_path)
    storage.replace_klines("00700", [bar("2024-01-02", 102.0)], db)
    monkeypatch.setattr(download_kline, "download_kline", lambda code, count: [])  # 停牌无新数据

    r = download_kline.update_code("00700", db_path=db, kline_dir=kline_dir)
    assert r == {"code": "00700", "mode": "empty", "new_bars": 0}  # 跳过不报错
    assert len(storage.load_klines("00700", db)) == 1


def test_update_code_full_replaces(tmp_path, monkeypatch):
    db, kline_dir = make_env(tmp_path)
    storage.replace_klines("00700", [bar("2024-01-02", 102.0), bar("2024-01-03", 103.0)], db)
    fetched = [bar("2024-02-01", 201.0)]
    calls = []

    def fake_download(code, count):
        calls.append(count)
        return fetched

    monkeypatch.setattr(download_kline, "download_kline", fake_download)

    r = download_kline.update_code("00700", db_path=db, kline_dir=kline_dir, full=True)
    assert r["mode"] == "full"
    assert calls == [2]  # 重拉条数沿用库中现有条数

    df = storage.load_klines("00700", db)
    assert list(df["date"]) == ["2024-02-01"]  # 旧数据被清除，新数据写入


def test_update_code_auto_full_when_no_existing(tmp_path, monkeypatch):
    db, kline_dir = make_env(tmp_path)
    monkeypatch.setattr(download_kline, "download_kline",
                        lambda code, count: [bar("2024-01-02", 102.0), bar("2024-01-03", 103.0)])

    r = download_kline.update_code("00700", db_path=db, kline_dir=kline_dir)
    assert r == {"code": "00700", "mode": "auto-full", "new_bars": 2}
    assert len(storage.load_klines("00700", db)) == 2


def test_update_all_summary(tmp_path, monkeypatch):
    db, kline_dir = make_env(tmp_path)
    storage.replace_klines("00700", [bar("2024-01-02", 102.0)], db)
    storage.replace_klines("01810", [bar("2024-01-02", 202.0)], db)
    storage.replace_klines("00005", [bar("2024-01-02", 52.0)], db)

    def fake_download(code, count):
        if code == "00700":
            return [bar("2024-01-02", 102.0), bar("2024-01-03", 103.0)]  # 1 条新增
        if code == "01810":
            return [bar("2024-01-02", 202.0)]  # 无新数据
        raise download_kline.requests.RequestException("boom")

    monkeypatch.setattr(download_kline, "download_kline", fake_download)
    summary = download_kline.update_all(db_path=db, kline_dir=kline_dir)
    assert summary == {"added": 1, "updated": 1, "unchanged": 1, "failed": 1}
