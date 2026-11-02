# -*- coding: utf-8 -*-
"""采集后台线程：跑 Pipeline，把进度事件和日志转到界面。"""
from PyQt5.QtCore import QThread, pyqtSignal

from core.run_control import RunControl

from .qt_log_handler import QtLogHandler


class CollectWorker(QThread):
    # 进度事件（字典）
    progress = pyqtSignal(dict)
    # 全部结束，回传 summary
    finished_run = pyqtSignal(dict)

    def __init__(self, limit=None, resume: bool = True, parent=None):
        super().__init__(parent)
        self.limit = limit
        self.resume = resume
        # 运行控制在主线程创建，界面通过它暂停、继续、停止，线程安全
        self.control = RunControl()
        # 日志 handler 在主线程创建，信号连到日志窗口
        self.log_handler = QtLogHandler()

    def request_pause(self):
        self.control.request_pause()

    def request_resume(self):
        self.control.request_resume()

    def request_stop(self):
        self.control.request_stop()

    def run(self):
        from core.logger import add_global_handler, remove_global_handler
        from core.pipeline import Pipeline

        add_global_handler(self.log_handler)
        try:
            pipe = Pipeline(
                limit=self.limit,
                resume=self.resume,
                progress_callback=lambda event: self.progress.emit(event),
                control=self.control,
            )
            summary = pipe.run()
        except Exception as e:
            summary = {"error": str(e), "stopped": False, "xlsx": "",
                       "review": "", "success": 0}
        finally:
            remove_global_handler(self.log_handler)

        self.finished_run.emit(summary)
