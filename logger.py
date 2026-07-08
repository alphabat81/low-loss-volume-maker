import json
import logging
from pathlib import Path


def setup_logger(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("low_loss_volume_maker")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def log_event(logger, event, **fields):
    logger.info(json.dumps({"event": event, **fields}, default=str, ensure_ascii=True))

