from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
def setup_logging(config: dict) -> logging.Logger:
    logger = logging.getLogger('patrolbot')
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')
    console = logging.StreamHandler(); console.setFormatter(fmt); logger.addHandler(console)
    log_path = Path(config.get('logging', {}).get('file', 'logs/patrolbot.log'))
    if not log_path.is_absolute():
        log_path = Path(__file__).resolve().parent.parent / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3); fh.setFormatter(fmt); logger.addHandler(fh)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    return logger
