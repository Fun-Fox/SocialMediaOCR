import os
import sys
import time
from loguru import logger

# 确保logs目录存在
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(log_dir, exist_ok=True)

# 启动时主动清理超过7天的旧日志文件
_RETENTION_SECONDS = 7 * 24 * 60 * 60  # 7天
_now = time.time()
for _filename in os.listdir(log_dir):
    _filepath = os.path.join(log_dir, _filename)
    if os.path.isfile(_filepath) and (_now - os.path.getmtime(_filepath)) > _RETENTION_SECONDS:
        try:
            os.remove(_filepath)
        except OSError:
            pass

# 移除loguru默认的stderr handler，避免重复输出
logger.remove()

# 控制台输出：仅WARNING及以上，减少干扰
logger.add(
    sink=sys.stderr,
    level="WARNING",
    format="<level>{level}</level> | {message}",
    colorize=True,
)

# 文件输出：INFO级别，按天轮转 + 大小上限，自动清理
logger.add(
    sink=os.path.join(log_dir, "run_{time:YYYY-MM-DD}.log"),
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {name}:{function}:{line} | {message}",
    rotation="50 MB",
    retention="7 days",
    compression="zip",
    encoding="utf-8",
    enqueue=True,
)