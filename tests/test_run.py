"""回测入口测试"""
import pandas as pd
import pytest

import storage
from backtest import run as run_module


def bar(date: str, close: float = 100.0) -> dict:
    return {"date": date, "open": close - 1.0, "close": close,
            "high": close + 1.0, "low": close - 2.0, "volume": 1000.0}


def test_load_kline_reads_sqlite(tmp_path):
    db = tmp_path / "test.db"
    storage.replace_klines("00700", [bar("2024-01-03", 103.0), bar("2024-01-02", 102.0)], db)

    df = run_module.load_kline("00700", db_path=db)
    assert len(df) == 2
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert pd.api.types.is_datetime64_any_dtype(df["date"])  # 日期转 datetime 供引擎用
    assert df["close"].tolist() == [102.0, 103.0]


def test_load_kline_empty_raises(tmp_path):
    db = tmp_path / "test.db"
    with pytest.raises(FileNotFoundError, match="download_kline"):
        run_module.load_kline("00700", db_path=db)
