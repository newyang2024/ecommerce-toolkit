# -*- coding: utf-8 -*-
"""把 logging 日志转成 Qt 信号，供界面实时显示。"""
import logging

from PyQt5.QtCore import QObject, pyqtSignal


class QtLogHandler(QObject, logging.Handler):
    # 一条格式化好的日志文本
    message = pyqtSignal(str)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        logging.Handler.__init__(self)
        self.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                              datefmt="%H:%M:%S")
        )

    def emit(self, record):
        try:
            self.message.emit(self.format(record))
        except Exception:
            pass
