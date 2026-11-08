# Quant Lab — 量化回测平台

通用型股票策略回测系统，支持多市场（港股、A 股等）历史数据回测。

## 功能

- 历史 K 线数据批量下载与存储（SQLite + JSON）
- 策略引擎（MA 金叉、自定义策略）
- 回测撮合（手续费、滑点、仓位管理）
- 回测报告（收益率曲线、胜率、最大回撤、夏普比率）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 下载历史数据
python scripts/download_kline.py --code 00700 --years 5

# 3. 运行回测
python -m backtest.run --code 00700 --strategy ma_cross
```

## 项目结构

```
quant-lab/
├── CLAUDE.md              # Claude Code 项目上下文
├── README.md              # 本文件
├── requirements.txt       # Python 依赖
├── config.py              # 全局配置
├── data/
│   ├── kline/             # K 线 JSON 文件
│   └── quant.db           # SQLite 数据库
├── scripts/
│   └── download_kline.py  # 历史数据下载
├── backtest/
│   ├── __init__.py
│   ├── engine.py          # 回测引擎
│   ├── strategy.py        # 策略定义
│   ├── indicators.py      # 技术指标
│   └── report.py          # 报告生成
└── tests/
    └── test_engine.py
```

## 与热力图项目的关系

- 共享数据目录：`cat/shared/BACKTEST_PLAN.md` 记录了技术约定
- 热力图项目：`cat/hongkong-etf`（Next.js，实时可视化）
- 共享 K 线数据：通过 JSON 文件互通

## 文档

详细技术方案见 `cat/shared/BACKTEST_PLAN.md`
