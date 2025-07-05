from utils.logger import setup_logger
from service.trading_service import TradingService
import time

logger = setup_logger(__name__)

def main():
    """应用主入口"""
    logger.info("应用启动...")

    # 初始化交易服务
    try:
        trading_service = TradingService()
        logger.info("交易服务初始化成功")
    except Exception as e:
        logger.error(f"交易服务初始化失败: {e}")
        return

    # 保持程序运行
    try:
        while True:
            # 执行交易逻辑
            trading_service.execute_trading_logic()

            # 等待30秒再执行下一次检查
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("应用正在关闭...")

if __name__ == "__main__":
    main()
