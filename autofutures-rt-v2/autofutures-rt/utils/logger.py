"""utils/logger.py"""
import logging, os
from datetime import datetime

def setup_logger():
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f"logs/bot_{datetime.now().strftime('%Y%m%d')}.log", "a", "utf-8")
        ]
    )
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return logging.getLogger("autofutures-rt")
