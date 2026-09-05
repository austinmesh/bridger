from loguru import logger

from bridger.config import LOG_PATH

LOGURU_FORMAT = (
    "<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

file_logger = logger.add(LOG_PATH, rotation="50 MB", retention="10 days", serialize=True, format=LOGURU_FORMAT)
