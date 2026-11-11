"""技术指标测试"""
import pandas as pd

from backtest.indicators import calc_trend_template, calc_volume_percentile, calc_volume_ratio


def test_volume_ratio_known_values():
    """已知数列手算验证：前 5 日均量 100，当日 200 → 量比 2.0"""
    vol = pd.Series([100.0, 100, 100, 100, 100, 200])
    ratio = calc_volume_ratio(vol, period=5)
    assert ratio.iloc[5] == 2.0


def test_volume_ratio_baseline_excludes_today():
    """基准不含当日：当日巨量不污染分母"""
    vol = pd.Series([10.0, 10, 10, 10, 10, 1000])
    ratio = calc_volume_ratio(vol, period=5)
    assert ratio.iloc[5] == 100.0  # 1000 / 10；若含当日分母会被拉高而失真


def test_volume_ratio_nan_before_baseline_ready():
    """基准不足 N 天时返回 NaN"""
    vol = pd.Series([100.0, 100, 100, 100, 100, 200])
    ratio = calc_volume_ratio(vol, period=5)
    assert ratio.iloc[:5].isna().all()  # 前 5 个（0~4）无基准
    assert not pd.isna(ratio.iloc[5])


def test_volume_ratio_period_parameter():
    """period 参数生效：N=3 时前 3 天无基准，第 4 天有值"""
    vol = pd.Series([10.0, 10, 10, 20])
    ratio = calc_volume_ratio(vol, period=3)
    assert ratio.iloc[:3].isna().all()
    assert ratio.iloc[3] == 2.0  # 20 / mean(10,10,10)


def test_volume_percentile_known_values():
    """已知数列手算验证：前 10 日 95 分位 = 1.0"""
    vol = pd.Series([1.0] * 10 + [100.0])
    p = calc_volume_percentile(vol, window=10, q=0.95)
    assert p.iloc[10] == 1.0


def test_volume_percentile_excludes_today():
    """分位基准不含当日：当日巨量不污染基准"""
    vol = pd.Series([1.0] * 10 + [100.0])
    p = calc_volume_percentile(vol, window=10, q=0.95)
    assert p.iloc[10] == 1.0  # 若含当日 95 分位会被抬高


def test_volume_percentile_nan_before_ready():
    """基准不足 window 天时返回 NaN"""
    vol = pd.Series([1.0] * 5)
    p = calc_volume_percentile(vol, window=10)
    assert p.isna().all()


# ---- 趋势模板（Minervini 7 条件）----

def _uptrend(n: int = 260) -> pd.Series:
    """匀速上涨 100 → 100+0.2(n-1)：模板条件全部满足"""
    return pd.Series([100.0 + 0.2 * i for i in range(n)])


def _downtrend(n: int = 260) -> pd.Series:
    """匀速下跌 200 → 200-0.4(n-1)：均线空头排列、MA200 下行"""
    return pd.Series([200.0 - 0.4 * i for i in range(n)])


def test_trend_template_all_true_in_uptrend():
    """匀速上涨中 7 条件全部满足"""
    tpl = calc_trend_template(_uptrend())
    assert bool(tpl.iloc[-1].all())


def test_trend_template_above_150_200_column():
    """条件1：尾日深跌到均线体系下方 → above_150_200 不满足"""
    s = _uptrend()
    s.iloc[-1] = 50.0
    tpl = calc_trend_template(s)
    assert not tpl["above_150_200"].iloc[-1]


def test_trend_template_ma150_gt_ma200_column():
    """条件2：长期阴跌均线空头排列 → ma150_gt_ma200 不满足"""
    tpl = calc_trend_template(_downtrend())
    assert not tpl["ma150_gt_ma200"].iloc[-1]


def test_trend_template_ma200_rising_column():
    """条件3：阴跌中 MA200 下行 → ma200_rising 不满足；上涨中满足"""
    assert calc_trend_template(_uptrend())["ma200_rising"].iloc[-1]
    assert not calc_trend_template(_downtrend())["ma200_rising"].iloc[-1]


def test_trend_template_ma50_above_column():
    """条件4：长期阴跌后单日暴涨——价在均线之上但 MA50 仍低于 MA200"""
    s = pd.Series([200.0 - 0.4 * i for i in range(259)] + [300.0])
    tpl = calc_trend_template(s)
    assert not tpl["ma50_above"].iloc[-1]
    assert tpl["above_150_200"].iloc[-1]  # 隔离性：条件1 仍满足，说明是条件4 自己失败


def test_trend_template_off_low_column():
    """条件5：尾日跌回 52 周低点附近 → 距低点不足 25%"""
    s = _uptrend()
    s.iloc[-1] = 110.0  # 52 周低点 ≈ 102，110 < 102×1.25
    tpl = calc_trend_template(s)
    assert not tpl["off_low"].iloc[-1]


def test_trend_template_near_high_column():
    """条件6：尾日距 52 周高点回撤超过 25% → near_high 不满足"""
    s = _uptrend()
    s.iloc[-1] = 100.0  # 52 周高点 ≈ 151.8，100 < 151.8×0.75
    tpl = calc_trend_template(s)
    assert not tpl["near_high"].iloc[-1]


def test_trend_template_above_ma50_column():
    """条件7：尾日跌破 MA50 → above_ma50 不满足"""
    s = _uptrend()
    s.iloc[-1] = 50.0
    tpl = calc_trend_template(s)
    assert not tpl["above_ma50"].iloc[-1]


def test_trend_template_unverifiable_is_false():
    """数据不足（窗口未满）无法判定的条件按不满足处理 → 整体模板不通过"""
    tpl = calc_trend_template(pd.Series([100.0 + 0.2 * i for i in range(100)]))
    assert not tpl["off_low"].any()        # 52 周窗口未满，无法判定
    assert not tpl["ma200_rising"].any()   # MA200 未就绪，无法判定
    assert not tpl.all(axis=1).any()       # 整体不通过（买入门槛取 AND）
