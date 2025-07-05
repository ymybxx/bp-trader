# config.py
import os
from dotenv import load_dotenv
from pathlib import Path
from utils.logger import setup_logger

logger = setup_logger(__name__)

# 获取项目根目录路径
ROOT_DIR = Path(__file__).parent.parent

env = os.getenv("ENV", "dev")
env_file = Path(__file__).parent / f".env.{env}"

# 修改判断逻辑，优先使用环境变量，环境变量不存在时才从文件加载
if env_file.exists():
    logger.info(f"从文件加载环境变量: {env_file}")
    load_dotenv(env_file)

# 打印加载后的环境变量
logger.info("加载的环境变量:")
logger.info(f"BACKPACK_API_KEY: {os.getenv('BACKPACK_API_KEY')[:10] if os.getenv('BACKPACK_API_KEY') else None}...")
logger.info(f"TRADING_SYMBOL: {os.getenv('TRADING_SYMBOL')}")
logger.info(f"TRADING_LEVERAGE: {os.getenv('TRADING_LEVERAGE')}")
logger.info(f"TRADING_AMOUNT: {os.getenv('TRADING_AMOUNT')}")

# Backpack API配置
BACKPACK_CONFIG = {
    "api_key": os.getenv("BACKPACK_API_KEY"),
    "private_key": os.getenv("BACKPACK_PRIVATE_KEY"),
    "base_url": os.getenv("BACKPACK_BASE_URL", "https://api.backpack.exchange"),
}

# 交易配置
TRADING_CONFIG = {
    "symbol": os.getenv("TRADING_SYMBOL", "SOL"),  # 交易代币
    "leverage": int(os.getenv("TRADING_LEVERAGE", 10)),  # 杠杆率
    "trade_amount": float(os.getenv("TRADING_AMOUNT", 100.0)),  # 单次交易额(USDT)
}

