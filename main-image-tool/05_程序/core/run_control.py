# -*- coding: utf-8 -*-
"""采集运行控制：统一管理暂停、继续、停止，线程安全，供后台线程和界面交互。"""
import threading
import time


class RunControl:
    """用两个事件分别表示暂停和停止，界面与后台线程通过方法通信。"""

    def __init__(self, poll_interval: float = 0.25):
        self._pause = threading.Event()
        self._stop = threading.Event()
        self._poll = poll_interval

    # ---------- 界面侧调用 ----------
    def request_pause(self):
        self._pause.set()

    def request_resume(self):
        self._pause.clear()

    def request_stop(self):
        self._stop.set()

    # ---------- 后台线程侧查询 ----------
    def is_paused(self) -> bool:
        return self._pause.is_set()

    def is_stopped(self) -> bool:
        return self._stop.is_set()

    def wait_if_paused(self) -> bool:
        """暂停时阻塞，直到恢复或停止。返回 True 表示等待期间被停止。"""
        while self._pause.is_set():
            if self._stop.is_set():
                return True
            time.sleep(self._poll)
        return self._stop.is_set()
