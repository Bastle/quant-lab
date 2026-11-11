# Quant Lab — 量化回测平台

通用型股票策略回测系统，支持多市场（港股、A 股等）历史数据回测。

## 功能

- 历史 K 线数据批量下载与存储（SQLite + JSON 双写，前复权 qfq）
- 策略引擎（MA 金叉、自定义策略）
- 回测撮合（手续费、滑点、仓位管理）
- 回测报告（收益率曲线、胜率、最大回撤、夏普比率）
- K 线日常增量更新 + 定期全量校正

## 环境要求

- Python 3.11+
- 依赖：`pandas`、`numpy`、`requests`（见 `requirements.txt`），测试用 `pytest`

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
```

> 本机备注：homebrew 的 Python 3.12 存在 pyexpat 损坏（`platform.mac_ver()` 返回空、pip 崩溃），
> 建议用 uv 托管的独立 Python 建 venv：
> `uv venv --python 3.12 --python-preference only-managed .venv && uv pip install --python .venv/bin/python -r requirements.txt pytest`

## 快速开始

```bash
# 1. 下载历史数据（单只 5 年，或批量拉恒生科技+恒生指数成分股共 105 只）
python scripts/download_kline.py --code 00700 --years 5
python scripts/download_kline.py --list all --years 5    # 约 11~15 分钟（限速 3 秒/请求）

# 2. 运行回测
python -m backtest.run --code 00700 --strategy ma_cross

# 3. 跑测试
python -m pytest tests/ -q
```

## 数据下载 / 更新命令参考

| 命令 | 作用 |
|------|------|
| `--code 00700 --years 5` | 单只下载 5 年（约 250 根/年）；无存量时自动全量，有存量时增量更新 |
| `--code 00700 --count 500` | 按条数下载 |
| `--list hstech\|hsi\|all --years 5` | 按成分股名单批量下载（all = 先恒生科技后恒生指数，重叠去重） |
| `--update-all` | 增量更新库中全部股票（拉最近 ~30 根，只写入新日期） |
| `--update-all --full` | 全量重拉替换，消除前复权漂移 |
| `--code 00700 --full` | 单只整段重拉替换 |
| `--no-json` | 不写 JSON 双写文件（只写 SQLite） |

**日常节奏**：收盘后跑 `--update-all`（约 5 分钟）；每月或分红密集期后跑一次 `--update-all --full`（约 10~12 分钟）。
无新数据的股票（停牌/退市）自动跳过并计数，不会报错。若某次返回条数明显少于库中条数（疑似分页中断），
护栏会拒绝整段替换、保留原历史，稍后重试即可。

⚠️ **前复权（qfq）取舍**：qfq 价格以最新价为基准回溯调整，分红除权后全部历史价格会被重算。
两次 `--full` 全量校正之间，增量追加的新 K 线与旧历史的复权基准可能短暂不一致。
MA 金叉类策略影响很小；做精确回测（事件驱动、分红策略）前请先跑一次 `--full`。

## 数据存储

- **SQLite**（`data/quant.db`，主存储）：`kline(code, date, open, close, high, low, volume)`，主键 `(code, date)`，同日期自动去重
- **JSON 双写**（`data/kline/*.json`）：`{updatedAt, data[]}` 格式，与热力图项目共享约定，便于跨项目互通
- **存量导入**：`python scripts/import_kline.py --dir <json目录>` 把共享格式 JSON 批量导入 SQLite（合并语义，不清历史），用于种子数据
- **成分股名单**（`data/index_constituents.json`）：恒生科技 30 + 恒生指数 95（去重 105 只），来自恒生指数官网，
  **季度调整时手动更新该文件**

## 回测使用

```bash
python -m backtest.run --code 00700 --strategy ma_cross          # MA 金叉，默认 MA5/20
python -m backtest.run --code 00700 --strategy ma_cross --short 10 --long 60
python -m backtest.run --code 00700 --strategy ma_cross --filter 200   # 趋势过滤
python -m backtest.run --code 00700 --strategy ma_cross --filter 200 --filter-exit  # +破线清仓
python -m backtest.run --code 00700 --strategy price_ma          # 价格×MA200 趋势跟随
python -m backtest.run --code 00700 --strategy price_ma --ma 60  # 换均线周期
python -m backtest.run --code 00700 --strategy template          # 趋势模板策略（7 条件翻转入场）
python -m backtest.run --code 00700 --vol-ratio 1.5              # 买入放量确认
python -m backtest.run --code 00700 --volume-exit                # 巨量出货卖出
python -m backtest.run --code 00700 --trailing-stop 8            # 移动止损 8%
python -m backtest.run --code 00700 --trend-template             # 趋势模板买入过滤
```

**趋势过滤**（`--filter N`，如 MA200）：金叉须发生在过滤均线上方才买入（过滤逆势反弹）；
只禁止开新仓，卖出仍由死叉决定。`--filter 0` 或不加 = 关闭。
**破线清仓**（`--filter-exit`，需配合 `--filter`）：收盘价跌破过滤均线当天强制卖出。
**量比放量确认**（`--vol-ratio X`）：买入信号当日量比（当日量 / 前 5 日均量）须 ≥ X 才买入，只禁止开新仓。
**巨量出货卖出**（`--volume-exit`）：连续 3 日成交量 ≥ 前 250 日 95 分位且 3 日累计下跌 → 卖出；
开启后替换死叉/下穿卖出。
**移动止损**（`--trailing-stop X`）：持仓期收盘价从最高收盘价回撤超过 X% → 卖出（优先级最高，可与以上任意组合）。
**趋势模板**（`--trend-template`）：Minervini 7 条件全满足才买入（价在 MA50/150/200 上、MA50>MA150>MA200、
MA200 上涨≥1 个月、高出 52 周低点 ≥25%、距 52 周高点 25% 以内）；任一不满足或数据不足 → 不买。只禁止开新仓。
**趋势模板策略**（`--strategy template`）：7 条件由不满足**翻转**为全满足的当天买入（不依赖上穿事件），
持续满足不重复买；卖出后须等模板重新翻转才再入场。卖出 = 收盘价下穿 MA（`--ma`，默认 200），
可叠加 `--volume-exit`（替换下穿）与 `--trailing-stop`。模板破坏不触发卖出——7 条件只做买入限制。

交易成本已内置（见 `config.py`）：佣金 0.03%（最低 5 元）、印花税 0.13%（卖出）、滑点 0.1%。
所有回测均按前复权价格计算。数据仅供研究，不构成任何交易建议。

## 项目结构

```
quant-lab/
├── CLAUDE.md              # Claude Code 项目上下文
├── README.md              # 本文件
├── requirements.txt       # Python 依赖
├── config.py              # 全局配置（路径、API、回测参数）
├── storage.py             # SQLite 存储层
├── data/
│   ├── kline/             # K 线 JSON（与热力图共享格式，已 gitignore）
│   ├── index_constituents.json  # 成分股名单（手工维护）
│   └── quant.db           # SQLite 数据库（已 gitignore）
├── scripts/
│   ├── download_kline.py  # 历史数据下载/更新
│   └── import_kline.py    # 存量 JSON 批量导入
├── backtest/
│   ├── engine.py          # 回测引擎（撮合、持仓、成本）
│   ├── strategy.py        # 策略定义（MA 金叉等）
│   ├── indicators.py      # 技术指标（MA 等）
│   └── report.py          # 报告生成
└── tests/                 # pytest 测试（39 例）
```

## 与热力图项目的关系

- 共享数据目录：`cat/shared/BACKTEST_PLAN.md` 记录了技术约定（API 用法、限速、评估指标）
- 热力图项目：`cat/hongkong-etf`（Next.js，实时可视化）
- 共享 K 线数据：通过 JSON 文件互通（本项目双写保持格式兼容）

## 文档

详细技术方案见 `cat/shared/BACKTEST_PLAN.md`
