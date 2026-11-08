"""全局配置"""
from pathlib import Path

# 路径
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
KLINE_DIR = DATA_DIR / "kline"
DB_PATH = DATA_DIR / "quant.db"
SHARED_DIR = PROJECT_ROOT.parent / "shared"

# 腾讯 K 线 API
TENCENT_KLINE_URL = "https://ifzq.gtimg.cn/appstock/app/fqkline/get"
API_RATE_LIMIT_SEC = 3  # 请求间隔（秒）

# 回测默认参数
DEFAULT_COMMISSION = 0.0003   # 佣金 0.03%
DEFAULT_STAMP_TAX = 0.0013    # 印花税 0.13%（卖出时收取）
DEFAULT_SLIPPAGE = 0.001      # 滑点 0.1%
INITIAL_CAPITAL = 1_000_000   # 初始资金 100 万

# 确保目录存在
KLINE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
