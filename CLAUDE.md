# CLAUDE.md — Quant Lab 项目上下文

> Claude Code 启动时会自动读取这个文件。

## 项目概述

Quant Lab — 通用型股票策略回测平台，支持多市场（港股、A 股等）历史数据回测。
与港股热力图项目（`cat/hongkong-etf`）共享数据，详见 `cat/shared/BACKTEST_PLAN.md`。

## 技术栈

- **语言**: Python 3.11+
- **数据处理**: pandas, numpy
- **数据库**: SQLite
- **数据源**: 腾讯 K 线 API

## 常用命令

```bash
pip install -r requirements.txt    # 安装依赖
python scripts/download_kline.py   # 下载历史数据
python -m backtest.run             # 运行回测
python -m pytest tests/            # 运行测试
```

## 工作规则

1. **一次只做一个功能**：从 README 待办中选一个任务
2. **修改前先确认**：读相关文件，理解影响范围
3. **验证后才标记完成**：运行测试确认通过
4. **中文交流**：对话和注释尽量使用中文

## 硬约束

1. 所有价格数据必须使用前复权（qfq）
2. 回测必须计算手续费和滑点
3. 敏感信息（API key）绝不提交到 git
4. 测试数据不得包含真实交易建议

## 关键文件

| 文件 | 用途 |
|------|------|
| `config.py` | 全局配置（路径、API、回测参数） |
| `backtest/engine.py` | 回测引擎（买卖撮合、持仓管理） |
| `backtest/strategy.py` | 策略定义（MA 金叉等） |
| `backtest/indicators.py` | 技术指标（MA、MACD 等） |
| `backtest/report.py` | 回测报告生成 |
| `scripts/download_kline.py` | 历史数据下载 |
| `data/kline/*.json` | K 线数据（与热力图项目共享格式） |

## 数据格式

K 线 JSON 格式（与热力图项目兼容）：
```json
{
  "updatedAt": 1716700000000,
  "data": [
    { "date": "2024-01-02", "open": 295.0, "close": 298.4, "high": 301.2, "low": 293.8, "volume": 12345678 }
  ]
}
```

## 相关项目

- **港股热力图**: `cat/hongkong-etf`（Next.js + React，实时可视化）
- **共享文档**: `cat/shared/BACKTEST_PLAN.md`（技术约定、API 用法）
