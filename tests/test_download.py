"""K 线下载脚本测试（mock requests，不发真实请求）"""
import json

import pytest

from config import API_RATE_LIMIT_SEC
from scripts import download_kline


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self) -> dict:
        return self._payload


def day_payload(items: list, field: str = "day", symbol: str = "hk00700") -> dict:
    return {"data": {symbol: {field: items}}}


def item(date: str, open_: str = "10", close: str = "11", high: str = "12", low: str = "9", volume: str = "100") -> list:
    return [date, open_, close, high, low, volume]


def bar(date: str, close: float = 100.0) -> dict:
    return {"date": date, "open": close - 1.0, "close": close,
            "high": close + 1.0, "low": close - 2.0, "volume": 1000.0}


def test_fetch_bars_parses_day_field(monkeypatch):
    monkeypatch.setattr(download_kline.time, "sleep", lambda s: None)
    monkeypatch.setattr(download_kline.requests, "get",
                        lambda url, timeout: FakeResponse(day_payload([item("2024-01-02", "295.0", "298.4", "301.2", "293.8", "12345678")])))

    bars = download_kline.fetch_bars("00700", 10)
    assert bars == [{"date": "2024-01-02", "open": 295.0, "close": 298.4,
                     "high": 301.2, "low": 293.8, "volume": 12345678.0}]


def test_fetch_bars_parses_qfqday_field(monkeypatch):
    monkeypatch.setattr(download_kline.time, "sleep", lambda s: None)
    monkeypatch.setattr(download_kline.requests, "get",
                        lambda url, timeout: FakeResponse(day_payload([item("2024-01-02")], field="qfqday")))

    bars = download_kline.fetch_bars("00700", 10)
    assert len(bars) == 1
    assert bars[0]["date"] == "2024-01-02"


def test_fetch_bars_filters_dirty_data(monkeypatch):
    monkeypatch.setattr(download_kline.time, "sleep", lambda s: None)
    items = [
        item("2024-01-02"),                    # 干净
        item("2024-01-03", open_="0"),          # open ≤ 0，过滤
        item("2024-01-04", close="-1"),         # close ≤ 0，过滤
    ]
    monkeypatch.setattr(download_kline.requests, "get",
                        lambda url, timeout: FakeResponse(day_payload(items)))

    bars = download_kline.fetch_bars("00700", 10)
    assert [b["date"] for b in bars] == ["2024-01-02"]


def test_download_kline_pagination_merges_and_dedupes(monkeypatch):
    # 两个日期窗口有重叠（01-03），合并后按日期去重排序
    win1 = [item("2024-01-03"), item("2024-01-04"), item("2024-01-05")]  # 近端窗口
    win2 = [item("2024-01-01"), item("2024-01-02"), item("2024-01-03")]  # 远端窗口，与近端重叠 01-03
    responses = iter([day_payload(win1), day_payload(win2)])
    calls = []
    slept = []

    def fake_get(url, timeout):
        calls.append(url)
        return FakeResponse(next(responses))

    monkeypatch.setattr(download_kline.time, "sleep", slept.append)
    monkeypatch.setattr(download_kline.requests, "get", fake_get)
    monkeypatch.setattr(download_kline, "MAX_BARS_PER_REQUEST", 3, raising=False)

    bars = download_kline.download_kline("00700", 5)
    assert [b["date"] for b in bars] == [
        "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    assert len(calls) == 2          # 分页两次请求
    assert "2024-01-02" in calls[1]  # 第二次请求以首窗最早日 -1 天为右边界
    # 每次请求前限速 sleep
    assert slept == [API_RATE_LIMIT_SEC] * 2


def test_download_kline_trims_to_count(monkeypatch):
    # API 返回多于请求条数时，保留最近 count 条
    monkeypatch.setattr(download_kline.time, "sleep", lambda s: None)
    items = [item(f"2024-01-{d:02d}") for d in range(1, 6)]
    monkeypatch.setattr(download_kline.requests, "get",
                        lambda url, timeout: FakeResponse(day_payload(items)))
    monkeypatch.setattr(download_kline, "MAX_BARS_PER_REQUEST", 3, raising=False)

    bars = download_kline.download_kline("00700", 3)
    assert [b["date"] for b in bars] == ["2024-01-03", "2024-01-04", "2024-01-05"]


def test_retry_on_transient_error(monkeypatch):
    calls = []

    def fake_get(url, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise download_kline.requests.RequestException("boom")
        return FakeResponse(day_payload([item("2024-01-02")]))

    slept = []
    monkeypatch.setattr(download_kline.time, "sleep", slept.append)
    monkeypatch.setattr(download_kline.requests, "get", fake_get)

    bars = download_kline.fetch_bars("00700", 10)
    assert len(bars) == 1
    assert len(calls) == 2          # 首次失败后重试成功
    assert len(slept) >= 2          # 限速 + 退避


def test_fetch_bars_malformed_response_returns_empty(monkeypatch):
    """API 返回异常形状（data 非字典 / day 含 null 元素）不抛异常"""
    monkeypatch.setattr(download_kline.time, "sleep", lambda s: None)

    # data 为列表（异常形状）→ 返回空
    monkeypatch.setattr(download_kline.requests, "get",
                        lambda url, timeout: FakeResponse({"data": []}))
    assert download_kline.fetch_bars("00700", 10) == []

    # day 数组含 null 元素 → 跳过该条，不抛
    monkeypatch.setattr(download_kline.requests, "get",
                        lambda url, timeout: FakeResponse(day_payload([None, item("2024-01-02")])))
    bars = download_kline.fetch_bars("00700", 10)
    assert [b["date"] for b in bars] == ["2024-01-02"]


def test_download_list_continues_on_unexpected_error(tmp_path, monkeypatch):
    """单只出现非预期异常不击穿批量循环，其余照常处理"""
    import storage
    db = tmp_path / "test.db"
    kline_dir = tmp_path / "kline"
    kline_dir.mkdir()
    path = make_constituents(tmp_path / "index_constituents.json")

    def fake_download(code, count=240):
        if code == "00700":
            return [{"date": "2024-01-02", "open": 10.0, "close": 11.0,
                     "high": 12.0, "low": 9.0, "volume": 100.0}]
        if code == "01810":
            raise AttributeError("unexpected shape")  # 非 RequestException
        return [{"date": "2024-01-03", "open": 20.0, "close": 21.0,
                 "high": 22.0, "low": 19.0, "volume": 200.0}]

    monkeypatch.setattr(download_kline, "download_kline", fake_download)
    summary = download_kline.download_list(
        "hstech", 240, db_path=db, kline_dir=kline_dir, constituents_path=path)

    assert summary == {"success": 2, "skipped": 0, "failed": 1}
    assert len(storage.load_klines("09618", db)) == 1  # 异常代码之后的股票照常落地


# ---- 保存双写 ----

def test_save_kline_dual_write(tmp_path):
    import storage
    db = tmp_path / "test.db"
    kline_dir = tmp_path / "kline"
    kline_dir.mkdir()
    bars = [{"date": "2024-01-02", "open": 10.0, "close": 11.0,
             "high": 12.0, "low": 9.0, "volume": 100.0}]

    download_kline.save_kline("00700", bars, db_path=db, kline_dir=kline_dir)

    # SQLite 写入
    df = storage.load_klines("00700", db)
    assert df["close"].tolist() == [11.0]
    # JSON 双写（共享格式）
    payload = json.loads((kline_dir / "00700.json").read_text(encoding="utf-8"))
    assert payload["data"] == bars
    assert isinstance(payload["updatedAt"], int)


def test_save_kline_no_json(tmp_path):
    import storage
    db = tmp_path / "test.db"
    kline_dir = tmp_path / "kline"
    kline_dir.mkdir()
    bars = [{"date": "2024-01-02", "open": 10.0, "close": 11.0,
             "high": 12.0, "low": 9.0, "volume": 100.0}]

    download_kline.save_kline("00700", bars, db_path=db, kline_dir=kline_dir, write_json=False)

    assert len(storage.load_klines("00700", db)) == 1
    assert not (kline_dir / "00700.json").exists()


def test_save_kline_guard_against_shrinking(tmp_path):
    """返回条数远少于库中现有条数时拒绝整段替换，防止静默删史"""
    import storage
    db = tmp_path / "test.db"
    kline_dir = tmp_path / "kline"
    kline_dir.mkdir()
    storage.replace_klines("00700", [bar(f"2024-01-{d:02d}") for d in range(2, 7)], db)  # 5 条

    with pytest.raises(ValueError, match="90%"):
        download_kline.save_kline("00700", [bar("2024-02-01"), bar("2024-02-02")],
                                  db_path=db, kline_dir=kline_dir)  # 只回 2 条
    assert len(storage.load_klines("00700", db)) == 5  # 旧历史完好


# ---- 批量模式 ----

def make_constituents(path):
    payload = {
        "updatedAt": "2026-11-08",
        "hstech": [{"code": "00700", "name": "騰訊控股"}, {"code": "01810", "name": "小米集團"},
                   {"code": "09618", "name": "京東集團"}],
        "hsi": [{"code": "00005", "name": "滙豐控股"}, {"code": "00700", "name": "騰訊控股"}],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_batch_codes(tmp_path):
    path = make_constituents(tmp_path / "index_constituents.json")

    assert download_kline.batch_codes("hstech", path) == ["00700", "01810", "09618"]
    assert download_kline.batch_codes("hsi", path) == ["00005", "00700"]
    # all = 先 hstech 后 hsi，重叠代码去重
    assert download_kline.batch_codes("all", path) == ["00700", "01810", "09618", "00005"]


def test_download_list_summary(tmp_path, monkeypatch):
    import storage
    db = tmp_path / "test.db"
    kline_dir = tmp_path / "kline"
    kline_dir.mkdir()
    path = make_constituents(tmp_path / "index_constituents.json")

    def fake_download(code, count=240):
        if code == "00700":
            return [{"date": "2024-01-02", "open": 10.0, "close": 11.0,
                     "high": 12.0, "low": 9.0, "volume": 100.0}]
        if code == "01810":
            return []  # 无数据（停牌/退市）
        raise download_kline.requests.RequestException("boom")

    monkeypatch.setattr(download_kline, "download_kline", fake_download)
    summary = download_kline.download_list(
        "hstech", 240, db_path=db, kline_dir=kline_dir, constituents_path=path)

    assert summary == {"success": 1, "skipped": 1, "failed": 1}
    assert len(storage.load_klines("00700", db)) == 1
    assert len(storage.load_klines("01810", db)) == 0
