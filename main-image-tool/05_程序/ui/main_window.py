# -*- coding: utf-8 -*-
"""主窗口：顶部环境区、三个标签页、状态栏。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .collect_tab import CollectTab
from .result_tab import ResultTab
from .review_tab import ReviewTab
from .widgets import StateItem


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("天猫主图智能信息提取工具")
        self.resize(1180, 760)

        self.browser_worker = None
        self.logged_in = False
        self.browser_ready = False

        self._build_tabs()
        self._build_topbar()
        self._build_layout()
        self._build_statusbar()
        self._load_link_info()
        # 启动时自动加载已有结果和复核清单，不用手动点刷新
        self.result_tab.reload()
        self.review_tab.reload()

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.collect_tab = CollectTab()
        self.result_tab = ResultTab()
        self.review_tab = ReviewTab()
        self.tabs.addTab(self.collect_tab, "采集控制")
        self.tabs.addTab(self.result_tab, "结果查看")
        self.tabs.addTab(self.review_tab, "复核清单")

        # 采集正常结束后自动刷新结果表格
        self.collect_tab.collect_finished.connect(self._on_collect_finished)

    def _on_collect_finished(self, stopped: bool):
        if not stopped:
            self.result_tab.reload()
            self.review_tab.reload()
        self.statusBar().showMessage(
            "采集已停止，进度已保存。" if stopped else "采集完成，结果已刷新。")

    def _build_topbar(self):
        self.topbar = QFrame()
        self.topbar.setObjectName("TopBar")

        title = QLabel("天猫主图智能信息提取")
        title.setObjectName("TopTitle")

        self.browser_state = StateItem("浏览器", "未连接")
        self.login_state = StateItem("登录", "未检测")
        self.link_label = QLabel("链接库：读取中")
        self.link_label.setObjectName("HintLabel")

        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(title)
        left.addLayout(self.browser_state)
        left.addLayout(self.login_state)
        left.addWidget(self.link_label)

        self.launch_btn = QPushButton("启动浏览器")
        self.launch_btn.setObjectName("Primary")
        self.launch_btn.clicked.connect(lambda: self._start_browser_worker("launch"))
        self.refresh_btn = QPushButton("重新检测")
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.clicked.connect(lambda: self._start_browser_worker("check"))

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(self.launch_btn)
        right.addWidget(self.refresh_btn)
        right.addStretch()

        bar = QHBoxLayout()
        bar.setContentsMargins(18, 14, 18, 14)
        bar.setSpacing(16)
        bar.addLayout(left)
        bar.addStretch()
        bar.addLayout(right)
        self.topbar.setLayout(bar)

    def _build_layout(self):
        central = QWidget()
        outer = QVBoxLayout()
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)
        outer.addWidget(self.topbar)
        outer.addWidget(self.tabs)
        central.setLayout(outer)
        self.setCentralWidget(central)

    def _build_statusbar(self):
        self.statusBar().showMessage("就绪。请先启动浏览器并确认天猫已登录。")

    def _load_link_info(self):
        try:
            from core.link_library import LinkLibrary
            from core.config_loader import load_config

            lib = LinkLibrary()
            lib.load()
            n = len(lib.unique_tasks())
            path = load_config()["paths"]["link_library"]
            self.link_label.setText(
                "链接库：%s，共 %d 个唯一商品（%d 行）"
                % (path, n, len(lib.items))
            )
        except Exception as e:
            self.link_label.setText("链接库读取失败：%s" % e)

    def _start_browser_worker(self, mode: str):
        # 已有检测在跑就不重复触发
        if self.browser_worker is not None and self.browser_worker.isRunning():
            return

        # 开始新一轮检测，先把登录状态置回检测中
        self.login_state.set_state("warn", "检测中")
        self.launch_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)

        from .browser_worker import BrowserWorker

        self.browser_worker = BrowserWorker(mode)
        self.browser_worker.state.connect(self._on_browser_state)
        self.browser_worker.done.connect(self._on_browser_done)
        self.browser_worker.start()

    def _on_browser_state(self, area: str, state: str, text: str):
        if area == "browser":
            self.browser_state.set_state(state, text)
        elif area == "login":
            self.login_state.set_state(state, text)

    def _on_browser_done(self, logged: bool, msg: str):
        self.logged_in = logged
        self.browser_ready = "已连接" in self.browser_state.text.text()
        self.launch_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.statusBar().showMessage(msg)
        # 通知采集控制标签页刷新可用状态
        self.collect_tab.refresh_env(self.browser_ready, logged)

    def closeEvent(self, event):
        # 关闭窗口时如果检测线程还在跑，先等它结束
        if self.browser_worker is not None and self.browser_worker.isRunning():
            self.browser_worker.wait(2000)
        event.accept()
