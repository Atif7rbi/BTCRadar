from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .config_loader import load_config, root_path


def get_logger(name: str = 'BTCRadar') -> logging.Logger:
    cfg = load_config()
    log_cfg = cfg.get('logging', {})
    log_path = root_path(log_cfg.get('path', 'logs/btc_radar.log'))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, str(log_cfg.get('level', 'INFO')).upper(), logging.INFO)

    base_logger = logging.getLogger('BTCRadar')
    base_logger.setLevel(level)
    base_logger.propagate = False

    if not base_logger.handlers:
        fmt = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')
        fh = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding='utf-8')
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        base_logger.addHandler(fh)
        base_logger.addHandler(sh)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    if name != 'BTCRadar' and name.startswith('BTCRadar.'):
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        logger.propagate = True
    return logger
