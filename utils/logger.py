import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

# 创建日志目录
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 日志格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logger(name: str = None) -> logging.Logger:
    """
    设置并返回一个logger实例
    
    Args:
        name: logger名称,默认使用调用模块的名称
        
    Returns:
        logging.Logger: 配置好的logger实例
    """
    logger = logging.getLogger(name)
    
    # 如果logger已经配置过handler,直接返回
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.DEBUG)
    # 防止向上传播到root logger
    logger.propagate = False
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)
    
    # 文件处理器
    file_handler = RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(file_handler)
    
    return logger

# 创建一个默认的root logger
logger = setup_logger("root") 