# -*- coding: utf-8 -*-
"""浏览器启动与登录检测的后台线程，避免阻塞界面。"""
from PyQt5.QtCore import QThread, pyqtSignal


class BrowserWorker(QThread):
    # 区域（browser/login）、状态（ok/idle/warn/err）、文字
    state = pyqtSignal(str, str, str)
    # 全部完成：是否已登录、提示消息
    done = pyqtSignal(bool, str)

    def __init__(self, mode: str = "launch", parent=None):
        super().__init__(parent)
        # mode: launch 启动并检测，check 只连接检测
        self.mode = mode

    def run(self):
        # 1. 需要时启动专用 Edge
        if self.mode == "launch":
            self.state.emit("browser", "warn", "启动中")
            try:
                import launch_edge

                launch_edge.main()
            except Exception as e:
                self.state.emit("browser", "err", "启动失败")
                self.done.emit(False, "浏览器启动失败：%s" % e)
                return

        # 2. 连接浏览器
        self.state.emit("browser", "warn", "连接中")
        from core.browser import BrowserManager

        browser = BrowserManager()
        try:
            browser.start()
        except Exception as e:
            self.state.emit("browser", "err", "未连接")
            self.done.emit(False, "浏览器未连接：%s" % e)
            return

        self.state.emit("browser", "ok", "已连接")

        # 3. 检查登录
        self.state.emit("login", "warn", "检测中")
        try:
            from core.login_check import check_login

            logged = check_login(browser.context)
        except Exception as e:
            self.state.emit("login", "err", "检测失败")
            browser.close()
            self.done.emit(False, "登录检测失败：%s" % e)
            return

        if logged:
            self.state.emit("login", "ok", "已登录")
            msg = "浏览器已连接，天猫已登录，可以开始采集。"
        else:
            self.state.emit("login", "warn", "未登录")
            msg = "浏览器已连接，但未检测到天猫登录，请在专用 Edge 里登录后再点重新检测。"

        browser.close()
        self.done.emit(logged, msg)
