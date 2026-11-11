"""策略测试（MA 金叉 + 趋势过滤 + 价格×均线）"""
import pandas as pd
import pytest

from backtest.indicators import calc_ma, calc_trend_template
from backtest.strategy import MACrossStrategy, PriceMACrossStrategy, Signal, TrendTemplateStrategy


def make_df(prices: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.DataFrame({
        "date": dates, "open": prices, "close": prices,
        "high": prices, "low": prices,
        "volume": volumes if volumes else [1000.0] * len(prices),
    })


# 高位平台 → 暴跌 → 小反弹：唯一金叉（idx 7）出现在 MA5 下方
BELOW_MA = [100, 100, 100, 100, 100, 50, 51, 52, 53, 48, 55]
# 上升趋势回调再涨：唯一金叉（idx 6）出现在 MA5 上方
ABOVE_MA = [50, 51, 52, 53, 48, 55, 56, 57, 58]


def test_filter_blocks_buy_below_ma():
    """金叉发生在过滤均线下方 → 买入信号被拦截"""
    df = make_df(BELOW_MA)
    unfiltered = MACrossStrategy(short_period=2, long_period=3).generate_signals(df)
    assert (unfiltered == Signal.BUY).sum() == 1  # 前提：确实有一次金叉

    filtered = MACrossStrategy(short_period=2, long_period=3, filter_period=5).generate_signals(df)
    assert (filtered == Signal.BUY).sum() == 0  # close < MA5，金叉作废
    assert filtered.iloc[7] == Signal.HOLD


def test_filter_allows_buy_above_ma():
    """金叉发生在过滤均线上方 → 买入信号正常放行（与不过滤一致）"""
    df = make_df(ABOVE_MA)
    unfiltered = MACrossStrategy(short_period=2, long_period=3).generate_signals(df)
    filtered = MACrossStrategy(short_period=2, long_period=3, filter_period=5).generate_signals(df)

    assert (filtered == Signal.BUY).sum() == 1  # 金叉被保留
    assert list(filtered) == list(unfiltered)   # 该数据集下过滤不改变任何信号


def test_filter_zero_disables_filter():
    """filter_period=0（默认）行为与不带过滤的原策略完全一致"""
    df = make_df(BELOW_MA)
    original = MACrossStrategy(short_period=2, long_period=3).generate_signals(df)
    default = MACrossStrategy(short_period=2, long_period=3).generate_signals(df)
    assert list(default) == list(original)
    # 关闭过滤时下方金叉照常买入（说明被拦是过滤的功劳，不是数据没金叉）
    assert default.iloc[7] == Signal.BUY


def test_filter_does_not_force_sell():
    """过滤只禁止开新仓：持仓期间信号不受过滤影响，死叉照常卖出"""
    df = make_df(BELOW_MA)
    filtered = MACrossStrategy(short_period=2, long_period=3, filter_period=5).generate_signals(df)
    # 数据集 1 中 idx 9 有死叉，close(48) < MA5，但卖出信号不受过滤影响
    assert filtered.iloc[9] == Signal.SELL


def test_filter_exit_forces_sell_below_ma():
    """filter_exit=True：收盘价跌破过滤均线当天强制卖出（即使没有死叉）"""
    df = make_df(BELOW_MA)
    base = MACrossStrategy(short_period=2, long_period=3, filter_period=5).generate_signals(df)
    exit_mode = MACrossStrategy(short_period=2, long_period=3, filter_period=5,
                                filter_exit=True).generate_signals(df)

    ma5 = calc_ma(df["close"], 5)
    below = [i for i in range(len(df)) if df["close"].iloc[i] <= ma5.iloc[i]]
    assert below, "前提：数据集中存在跌破 MA5 的交易日"
    # 跌破均线的每一天都发出卖出信号
    assert all(exit_mode.iloc[i] == Signal.SELL for i in below)
    # 而不强制清仓模式下这些日子大多不是卖出（说明信号是 filter_exit 的功劳）
    assert any(base.iloc[i] != Signal.SELL for i in below)


def test_filter_exit_keeps_buy_above_ma():
    """filter_exit=True：均线上方的金叉照常买入（只改卖出行为）"""
    df = make_df(ABOVE_MA)
    exit_mode = MACrossStrategy(short_period=2, long_period=3, filter_period=5,
                                filter_exit=True).generate_signals(df)
    assert (exit_mode == Signal.BUY).sum() == 1  # 均线上方金叉放行


def test_filter_exit_default_off():
    """filter_exit 默认关闭，行为与只禁止开新仓完全一致"""
    df = make_df(BELOW_MA)
    default = MACrossStrategy(short_period=2, long_period=3, filter_period=5).generate_signals(df)
    explicit = MACrossStrategy(short_period=2, long_period=3, filter_period=5,
                               filter_exit=False).generate_signals(df)
    assert list(default) == list(explicit)


# ---- 价格 × 均线（单均线趋势跟随）----

def test_price_ma_buy_on_cross_up():
    """价格上穿均线 → 买入"""
    df = make_df([10, 10, 10, 10, 14])  # MA3: idx3=10, idx4=11.33
    signals = PriceMACrossStrategy(period=3).generate_signals(df)
    assert signals.iloc[4] == Signal.BUY   # 14 上穿 MA3
    assert list(signals[:4]) == [Signal.HOLD] * 4


def test_price_ma_sell_on_cross_down():
    """价格下穿均线 → 卖出"""
    df = make_df([14, 14, 14, 14, 10])  # MA3: idx3=14, idx4=12.67
    signals = PriceMACrossStrategy(period=3).generate_signals(df)
    assert signals.iloc[4] == Signal.SELL  # 10 下穿 MA3
    assert list(signals[:4]) == [Signal.HOLD] * 4


def test_price_ma_no_signal_when_one_side():
    """价格一直在均线同侧（单边涨/跌）→ 无信号"""
    up = PriceMACrossStrategy(period=3).generate_signals(make_df([10, 11, 12, 13, 14]))
    down = PriceMACrossStrategy(period=3).generate_signals(make_df([14, 13, 12, 11, 10]))
    assert (up == Signal.HOLD).all()
    assert (down == Signal.HOLD).all()


def test_price_ma_no_signal_before_ma_ready():
    """均线历史不足（NaN）时不发信号"""
    df = make_df([10, 10, 10])  # MA3 仅 idx2 有效
    signals = PriceMACrossStrategy(period=3).generate_signals(df)
    assert (signals == Signal.HOLD).all()


def test_price_ma_default_period_200():
    """默认周期为 200 日"""
    assert PriceMACrossStrategy().period == 200


# ---- 量比过滤（放量确认，两个策略通用）----

# 金叉/上穿出现在 idx 6（前 6 天横盘 10，第 7 天涨到 14）
CROSS_PRICES = [10, 10, 10, 10, 10, 10, 14]


def test_vol_ratio_blocks_buy_on_low_volume():
    """金叉当日量比低于阈值（缩量）→ 买入被拦截"""
    df = make_df(CROSS_PRICES, [100.0] * 7)  # 量比 = 1.0
    unfiltered = MACrossStrategy(short_period=2, long_period=3).generate_signals(df)
    assert unfiltered.iloc[6] == Signal.BUY  # 前提：idx6 有金叉

    filtered = MACrossStrategy(short_period=2, long_period=3, vol_ratio=1.5).generate_signals(df)
    assert filtered.iloc[6] == Signal.HOLD


def test_vol_ratio_allows_buy_on_surge():
    """金叉当日量比达标（放量）→ 买入放行"""
    df = make_df(CROSS_PRICES, [100.0] * 6 + [200.0])  # idx6 量比 = 2.0
    filtered = MACrossStrategy(short_period=2, long_period=3, vol_ratio=1.5).generate_signals(df)
    assert filtered.iloc[6] == Signal.BUY


def test_vol_ratio_nan_not_blocked():
    """量比历史不足（NaN）不拦截（金叉在第 6 天前，量比无法计算）"""
    df = make_df([10, 10, 10, 10, 14], [100.0] * 5)  # 金叉 idx4，量比 NaN
    filtered = MACrossStrategy(short_period=2, long_period=3, vol_ratio=5.0).generate_signals(df)
    assert filtered.iloc[4] == Signal.BUY


def test_vol_ratio_default_off():
    """vol_ratio=0（默认）行为与不带量比过滤完全一致"""
    df = make_df(CROSS_PRICES, [100.0] * 7)
    default = MACrossStrategy(short_period=2, long_period=3).generate_signals(df)
    explicit = MACrossStrategy(short_period=2, long_period=3, vol_ratio=0).generate_signals(df)
    assert list(default) == list(explicit)
    assert default.iloc[6] == Signal.BUY  # 无过滤时缩量金叉照常买


def test_vol_ratio_does_not_block_sell():
    """量比过滤只作用于买入：死叉当日缩量照常卖出"""
    df = make_df([14, 14, 14, 14, 14, 14, 10], [100.0] * 7)  # 死叉 idx6，量比 1.0
    filtered = MACrossStrategy(short_period=2, long_period=3, vol_ratio=1.5).generate_signals(df)
    assert filtered.iloc[6] == Signal.SELL


def test_vol_ratio_price_ma_blocks_and_allows():
    """价格×均线策略同样受量比过滤：缩量上穿拦截、放量上穿放行"""
    low = make_df(CROSS_PRICES, [100.0] * 7)            # 量比 1.0
    high = make_df(CROSS_PRICES, [100.0] * 6 + [200.0])  # 量比 2.0
    assert PriceMACrossStrategy(period=3, vol_ratio=1.5).generate_signals(low).iloc[6] == Signal.HOLD
    assert PriceMACrossStrategy(period=3, vol_ratio=1.5).generate_signals(high).iloc[6] == Signal.BUY


# ---- 巨量出货卖出（B+V1：连续 3 日量≥250日95分位 且 3日累计下跌）----

def make_spike_df(prices_tail: list[float], volumes_tail: list[float], n: int = 257) -> pd.DataFrame:
    """前 n 天横盘 100（成交量 80~120 循环，95 分位≈120），尾部接自定义价格/成交量"""
    prices = [100.0] * n + prices_tail
    cyc = [80.0, 90.0, 100.0, 110.0, 120.0]
    volumes = (cyc * (n // 5 + 1))[:n] + volumes_tail
    return make_df(prices, volumes)


def test_volume_exit_sells_on_third_day():
    """连续 3 日巨量且累计下跌 → 第 3 日收盘卖出"""
    df = make_spike_df([95.0, 90.0, 85.0], [200.0, 200.0, 200.0])
    signals = MACrossStrategy(2, 3, volume_exit=True).generate_signals(df)
    assert signals.iloc[257] == Signal.HOLD  # 第 1 天不卖
    assert signals.iloc[258] == Signal.HOLD  # 第 2 天不卖
    assert signals.iloc[259] == Signal.SELL  # 第 3 天卖


def test_volume_exit_requires_cumulative_decline():
    """3 日巨量但期间累计上涨 → 不卖"""
    df = make_spike_df([105.0, 110.0, 115.0], [200.0, 200.0, 200.0])
    signals = MACrossStrategy(2, 3, volume_exit=True).generate_signals(df)
    assert (signals == Signal.SELL).sum() == 0


def test_volume_exit_requires_three_big_days():
    """收跌但只有 2 日巨量（第 3 日缩量）→ 不卖"""
    df = make_spike_df([95.0, 90.0, 85.0], [200.0, 200.0, 100.0])
    signals = MACrossStrategy(2, 3, volume_exit=True).generate_signals(df)
    assert (signals == Signal.SELL).sum() == 0


def test_volume_exit_replaces_death_cross():
    """开启后死叉不再卖出（由巨量出货规则接管）"""
    df = make_spike_df([95.0], [100.0])  # 横盘后一根阴线 → 死叉
    default = MACrossStrategy(2, 3).generate_signals(df)
    assert default.iloc[257] == Signal.SELL  # 原模式死叉卖出

    exit_mode = MACrossStrategy(2, 3, volume_exit=True).generate_signals(df)
    assert (exit_mode == Signal.SELL).sum() == 0  # 非巨量出货，不卖


def test_volume_exit_price_ma_sells_on_third_day():
    """价格×均线策略同样启用巨量出货卖出"""
    df = make_spike_df([95.0, 90.0, 85.0], [200.0, 200.0, 200.0])
    signals = PriceMACrossStrategy(period=3, volume_exit=True).generate_signals(df)
    assert signals.iloc[259] == Signal.SELL
    assert signals.iloc[257] == Signal.HOLD
    assert signals.iloc[258] == Signal.HOLD


# ---- 移动止损（吊灯式：收盘价从持仓期最高收盘价回撤 X% → 卖出）----

# idx6 金叉买入（close 14），idx8 见顶 18，idx9 收 16.2 恰好触及 10% 回撤线
STOP_PRICES = [10, 10, 10, 10, 10, 10, 14, 16, 18, 16.2]


def test_trailing_stop_sells_on_drawdown():
    """持仓期收盘价从最高收盘价回撤触及 X% → 当日卖出"""
    df = make_df(STOP_PRICES)
    signals = MACrossStrategy(2, 3, trailing_stop=0.1).generate_signals(df)
    assert signals.iloc[9] == Signal.SELL   # peak 18，16.2 <= 18×0.9 触发
    assert signals.iloc[7] == Signal.HOLD   # 回撤未触及前不动
    assert signals.iloc[8] == Signal.HOLD


def test_trailing_stop_no_trigger_without_drawdown():
    """回撤未触及止损线 → 不卖"""
    df = make_df([10, 10, 10, 10, 10, 10, 14, 16, 18, 16.5])  # 16.5 > 18×0.9
    signals = MACrossStrategy(2, 3, trailing_stop=0.1).generate_signals(df)
    assert (signals == Signal.SELL).sum() == 0


def test_trailing_stop_follows_new_peak():
    """止损基准跟随持仓期最高价抬高（吊灯语义），不是固定买入价"""
    df = make_df([10, 10, 10, 10, 10, 10, 14, 16, 18, 20, 22, 19.5])
    signals = MACrossStrategy(2, 3, trailing_stop=0.1).generate_signals(df)
    assert signals.iloc[10] == Signal.HOLD  # 新高日不触发
    assert signals.iloc[11] == Signal.SELL  # peak 22 → 19.5 <= 19.8 触发
    # 若基准停在买入价 14 或首个峰值 18，19.5 远高于对应止损线 12.6/16.2，不会卖


def test_trailing_stop_default_off():
    """trailing_stop=0（默认）行为与不带止损完全一致"""
    df = make_df(STOP_PRICES)
    default = MACrossStrategy(2, 3).generate_signals(df)
    explicit = MACrossStrategy(2, 3, trailing_stop=0).generate_signals(df)
    assert list(default) == list(explicit)
    assert default.iloc[9] == Signal.HOLD   # 无止损时不触发卖出


def test_trailing_stop_reentry_and_peak_reset():
    """止损后下一个买入信号正常再入场，且新仓基准从新买入价重新跟踪"""
    df = make_df([10, 10, 10, 10, 10, 10, 14, 16, 18, 16.2, 13, 10, 10, 14, 13])
    signals = MACrossStrategy(2, 3, trailing_stop=0.1).generate_signals(df)
    assert signals.iloc[9] == Signal.SELL    # 止损离场
    assert signals.iloc[13] == Signal.BUY    # 重新金叉买入
    assert signals.iloc[14] == Signal.HOLD   # 新仓 peak=14，13 > 12.6 不触发；
    # 若错误沿用旧 peak 18（止损线 16.2）会被误卖


def test_trailing_stop_price_ma():
    """价格×均线策略同样启用移动止损"""
    df = make_df([10, 10, 10, 10, 10, 14, 16, 18, 20, 18])
    signals = PriceMACrossStrategy(period=5, trailing_stop=0.1).generate_signals(df)
    assert signals.iloc[5] == Signal.BUY    # 14 上穿 MA5
    assert signals.iloc[9] == Signal.SELL   # peak 20，18 <= 20×0.9 触发
    # 前提核对：不带止损时 idx9 无下穿（18 仍高于 MA5=17.2），不是别的信号在卖
    assert PriceMACrossStrategy(period=5).generate_signals(df).iloc[9] != Signal.SELL


# ---- 趋势模板买入过滤（Minervini 7 条件，全满足才买）----

def make_template_df(volumes: list[float] | None = None) -> pd.DataFrame:
    """300 天匀速上涨 + 尾部下探回升（idx 302 金叉/上穿），模板 7 条件在 idx302 全满足"""
    prices = [100.0 + 0.2 * i for i in range(300)] + [158.0, 157.0, 161.0]
    return make_df(prices, volumes)


def make_downtrend_df() -> pd.DataFrame:
    """300 天匀速阴跌 + 尾部反弹（idx 302 金叉/上穿），模板条件不满足"""
    prices = [200.0 - 0.35 * i for i in range(300)] + [95.0, 94.0, 102.0]
    return make_df(prices)


def test_trend_template_allows_buy_in_uptrend():
    """模板 7 条件满足 → 金叉正常放行（与不开模板一致）"""
    df = make_template_df()
    off = MACrossStrategy(2, 3).generate_signals(df)
    on = MACrossStrategy(2, 3, trend_template=True).generate_signals(df)
    assert off.iloc[302] == Signal.BUY   # 前提：idx302 有金叉
    assert on.iloc[302] == Signal.BUY    # 模板满足 → 放行


def test_trend_template_blocks_buy_in_downtrend():
    """阴跌途中的反弹金叉被模板拦截"""
    df = make_downtrend_df()
    off = MACrossStrategy(2, 3).generate_signals(df)
    on = MACrossStrategy(2, 3, trend_template=True).generate_signals(df)
    assert (off == Signal.BUY).sum() >= 1   # 前提：确有金叉
    assert (on == Signal.BUY).sum() == 0    # 模板拦截


def test_trend_template_blocks_when_data_insufficient():
    """52 周窗口未满、无法判定 → 不买"""
    df = make_df([10, 10, 10, 10, 10, 10, 14])  # idx6 金叉，但仅 7 天数据
    off = MACrossStrategy(2, 3).generate_signals(df)
    on = MACrossStrategy(2, 3, trend_template=True).generate_signals(df)
    assert off.iloc[6] == Signal.BUY
    assert (on == Signal.BUY).sum() == 0


def test_trend_template_default_off():
    """trend_template 默认关闭，行为完全一致"""
    df = make_template_df()
    default = MACrossStrategy(2, 3).generate_signals(df)
    explicit = MACrossStrategy(2, 3, trend_template=False).generate_signals(df)
    assert list(default) == list(explicit)


def test_trend_template_and_vol_ratio_stack():
    """模板与量比叠加为 AND：模板满足但金叉当日缩量 → 不买"""
    df = make_template_df([100.0] * 303)  # idx302 量比 1.0
    both = MACrossStrategy(2, 3, trend_template=True, vol_ratio=1.5).generate_signals(df)
    assert (both == Signal.BUY).sum() == 0


def test_trend_template_price_ma_blocks_and_allows():
    """价格×均线策略同样受模板门控"""
    up = make_template_df()
    down = make_downtrend_df()
    assert PriceMACrossStrategy(period=3, trend_template=True).generate_signals(up).iloc[302] == Signal.BUY
    assert (PriceMACrossStrategy(period=3, trend_template=True).generate_signals(down) == Signal.BUY).sum() == 0


# ---- 趋势模板策略（7 条件翻转日即买入，不依赖上穿事件）----

def test_template_strategy_buys_on_flip_day():
    """模板由不满足翻转为满足的当天 → 买入；持续满足不重复买"""
    df = make_template_df()
    signals = TrendTemplateStrategy().generate_signals(df)
    assert signals.iloc[249] == Signal.BUY     # 52 周窗口刚满、7 条件首次全满足
    assert (signals == Signal.BUY).sum() == 1  # idx249~302 持续满足也只买一次
    # 前提：同数据下 MA200 上穿策略买不到（全程无上穿事件）——去掉上穿才是入场关键
    assert (PriceMACrossStrategy(period=200).generate_signals(df) == Signal.BUY).sum() == 0


def test_template_strategy_no_buy_when_never_satisfied():
    """模板从未全满足 → 全程不买"""
    df = make_downtrend_df()
    signals = TrendTemplateStrategy().generate_signals(df)
    assert (signals == Signal.BUY).sum() == 0


def test_template_strategy_no_buy_when_data_insufficient():
    """52 周窗口未满、无法判定 → 不买"""
    df = make_df([100.0 + 0.2 * i for i in range(240)])
    signals = TrendTemplateStrategy().generate_signals(df)
    assert (signals == Signal.BUY).sum() == 0


def test_template_strategy_no_rebuy_without_reflip():
    """B+V1 卖出后模板仍满足（未翻转）→ 不回补，须等重新翻转"""
    cyc = [80.0, 90.0, 100.0, 110.0, 120.0]
    prices = [100.0 + 0.2 * i for i in range(300)] + [158.0, 157.0, 156.0, 157.0, 158.0, 159.0]
    volumes = (cyc * 61)[:300] + [200.0, 200.0, 200.0, 100.0, 100.0, 100.0]
    df = make_df(prices, volumes)
    signals = TrendTemplateStrategy(volume_exit=True).generate_signals(df)
    assert signals.iloc[249] == Signal.BUY    # 翻转买入
    assert signals.iloc[302] == Signal.SELL   # B+V1 第 3 日卖出（3 日巨量 + 累计下跌）
    assert (signals == Signal.BUY).sum() == 1  # 卖出后模板未破坏 → 无翻转 → 不回补


def test_template_strategy_rebuys_on_next_flip():
    """任何卖出后，模板重新经历「不满足→满足」翻转 → 再次买入"""
    prices = ([100.0 + 0.2 * i for i in range(300)]              # 翻转 @249
              + [150.0 - 2.0 * k for k in range(25)]             # 崩跌破坏模板
              + [108.0 + 0.3 * k for k in range(300)])           # 修复后 @500 再翻转
    df = make_df(prices)
    signals = TrendTemplateStrategy().generate_signals(df)
    buy_days = [i for i in range(len(df)) if signals.iloc[i] == Signal.BUY]
    tpl_ok = calc_trend_template(df["close"]).all(axis=1)
    flip_days = [i for i in range(len(df))
                 if tpl_ok.iloc[i] and not (tpl_ok.iloc[i - 1] if i else False)]
    assert buy_days == flip_days   # 买入日恰好就是模板翻转日
    assert len(buy_days) == 2      # 崩跌拆成两段趋势，两次翻转


def test_template_strategy_sells_on_cross_down():
    """默认卖出 = 收盘价下穿 MA200"""
    prices = [100.0 + 0.2 * i for i in range(300)] + [158.0, 80.0]
    df = make_df(prices)
    signals = TrendTemplateStrategy().generate_signals(df)
    assert signals.iloc[249] == Signal.BUY    # 翻转买入
    assert signals.iloc[301] == Signal.SELL   # 80 下穿 MA200（模板破坏不卖，是下穿在卖）


def test_template_strategy_template_break_does_not_sell():
    """仅模板破坏（跌回 MA50 下方但未下穿 MA200）→ 不卖：7 条件只管买入"""
    prices = [100.0 + 0.2 * i for i in range(300)] + [145.0]  # 145 < MA50≈154.8 但 > MA200≈140
    df = make_df(prices)
    signals = TrendTemplateStrategy().generate_signals(df)
    assert signals.iloc[249] == Signal.BUY
    assert (signals == Signal.SELL).sum() == 0


def test_template_strategy_volume_exit_replaces_cross_down():
    """volume_exit=True：巨量出货替换下穿卖出，普通暴跌不再触发"""
    prices = [100.0 + 0.2 * i for i in range(300)] + [158.0, 80.0]
    cyc = [80.0, 90.0, 100.0, 110.0, 120.0]
    volumes = (cyc * 61)[:302]
    df = make_df(prices, volumes)
    assert TrendTemplateStrategy().generate_signals(df).iloc[301] == Signal.SELL  # 前提：下穿会卖

    exit_mode = TrendTemplateStrategy(volume_exit=True).generate_signals(df)
    assert (exit_mode == Signal.SELL).sum() == 0  # 无巨量出货形态 → 不卖


def test_template_strategy_trailing_stop():
    """移动止损叠加生效：从峰值回撤触及 → 卖出"""
    prices = [100.0 + 0.2 * i for i in range(300)] + [165.0, 175.0, 155.0]
    df = make_df(prices)
    signals = TrendTemplateStrategy(trailing_stop=0.1).generate_signals(df)
    assert signals.iloc[249] == Signal.BUY    # 翻转买入
    assert signals.iloc[302] == Signal.SELL   # peak 175，155 <= 157.5 触发
    # 前提核对：不带止损时 idx302 无下穿（155 仍高于 MA200≈140.5），是止损在卖
    assert TrendTemplateStrategy().generate_signals(df).iloc[302] != Signal.SELL
