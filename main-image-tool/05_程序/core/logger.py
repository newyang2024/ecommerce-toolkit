# -*- coding: utf-8 -*-
"""日志：控制台加按天滚动的文件日志。"""
import logging
from datetime import datetime
from pathlib import Path

from .config_loader import PROGRAM_ROOT, load_config, resolve_path

_logger_cache = {}
_extra_handlers = []


def add_global_handler(handler):
    """注册一个全局附加日志 handler，所有 get_logger 创建的日志器都会带上。"""
    if handler not in _extra_handlers:
        _extra_handlers.append(handler)
    for lg in _logger_cache.values():
        if handler not in lg.handlers:
            lg.addHandler(handler)


def remove_global_handler(handler):
    """移除全局附加日志 handler。"""
    if handler in _extra_handlers:
        _extra_handlers.remove(handler)
    for lg in _logger_cache.values():
        if handler in lg.handlers:
            lg.removeHandler(handler)


def get_logger(name: str = "main") -> logging.Logger:
    if name in _logger_cache:
        return _logger_cache[name]

    logger = logging.getLogger("zhutu_%s" % name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 控制台
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 文件，按天命名；配置取不到时退回程序根目录下的 logs
    try:
        cfg = load_config()
        log_dir = resolve_path(cfg["paths"]["log_dir"])
    except Exception:
        log_dir = PROGRAM_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / ("run_%s.log" % datetime.now().strftime("%Y%m%d"))
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    for h in _extra_handlers:
        logger.addHandler(h)

    logger.info("日志文件: %s", log_file)
    _logger_cache[name] = logger
    return logger
