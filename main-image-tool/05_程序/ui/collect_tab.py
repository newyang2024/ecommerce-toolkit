# -*- coding: utf-8 -*-
"""采集控制标签页：开始/停止、进度、统计、实时日志。"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .app_style import COLOR_OK, COLOR_WARN, COLOR_ERR
from .widgets import StatCard


class CollectTab(QWidget):
    # 采集结束时发出，参数为是否是停止（True 表示中途停止，False 表示正常完成）
    collect_finished = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.browser_ready = False
        self.logged_in = False
        self.worker = None
        self.total = 0
        self.paused = False

        self._build_controls()
        self._build_progress()
        self._build_log()

        outer = QVBoxLayout()
        outer.setSpacing(12)
        outer.addWidget(self.controls_box)
        outer.addWidget(self.progress_box)
        outer.addWidget(self.log_box, 1)
        self.setLayout(outer)

    # ---------- 界面搭建 ----------
    def _build_controls(self):
        self.controls_box = QGroupBox("采集设置")

        # 采集范围
        self.scope_all = QRadioButton("全部商品")
        self.scope_all.setChecked(True)
        self.scope_part = QRadioButton("前")
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 200)
        self.limit_spin.setValue(10)
        self.limit_spin.setEnabled(False)
        self.limit_spin.setFixedWidth(70)
        unit = QLabel("个")
        self.scope_all.toggled.connect(
            lambda: self.limit_spin.setEnabled(self.scope_part.isChecked()))
        self.scope_part.toggled.connect(
            lambda: self.limit_spin.setEnabled(self.scope_part.isChecked()))

        # 断点续跑
        self.resume_check = QCheckBox("断点续跑（跳过已完成商品）")
        self.resume_check.setChecked(True)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self.scope_all)
        row1.addWidget(self.scope_part)
        row1.addWidget(self.limit_spin)
        row1.addWidget(unit)
        row1.addSpacing(24)
        row1.addWidget(self.resume_check)
        row1.addStretch()

        # 按钮
        self.start_btn = QPushButton("开始采集")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self._on_start)
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause)
        self.resume_btn = QPushButton("继续")
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self._on_resume)
        self.stop_btn = QPushButton("停止采集")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)

        row2 = QHBoxLayout()
        row2.addWidget(self.start_btn)
        row2.addWidget(self.pause_btn)
        row2.addWidget(self.resume_btn)
        row2.addWidget(self.stop_btn)
        row2.addStretch()

        box = QVBoxLayout()
        box.setSpacing(12)
        box.addLayout(row1)
        box.addLayout(row2)
        self.controls_box.setLayout(box)

    def _build_progress(self):
        self.progress_box = QGroupBox("采集进度")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("未开始")

        self.current_label = QLabel("等待开始")
        self.current_label.setObjectName("HintLabel")

        self.stat_success = StatCard("成功", "0", COLOR_OK)
        self.stat_failed = StatCard("失败", "0", COLOR_ERR)
        self.stat_review = StatCard("待复核", "0", COLOR_WARN)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(self.stat_success)
        cards.addWidget(self.stat_failed)
        cards.addWidget(self.stat_review)

        box = QVBoxLayout()
        box.setSpacing(10)
        box.addWidget(self.progress_bar)
        box.addWidget(self.current_label)
        box.addLayout(cards)
        self.progress_box.setLayout(box)

    def _build_log(self):
        self.log_box = QGroupBox("实时日志")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setObjectName("LogView")

        box = QVBoxLayout()
        box.addWidget(self.log_view)
        self.log_box.setLayout(box)

    # ---------- 环境状态 ----------
    def refresh_env(self, browser_ready: bool, logged_in: bool):
        self.browser_ready = browser_ready
        self.logged_in = logged_in

    # ---------- 开始/停止 ----------
    def _on_start(self):
        if not (self.browser_ready and self.logged_in):
            self._append_log("请先在顶部启动浏览器并确认天猫已登录。")
            return

        limit = None
        if self.scope_part.isChecked():
            limit = self.limit_spin.value()
        resume = self.resume_check.isChecked()

        from .collect_worker import CollectWorker

        self.paused = False
        self.worker = CollectWorker(limit=limit, resume=resume)
        self.worker.log_handler.message.connect(self._append_log)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_run.connect(self._on_finished)

        self._set_running(True)
        self.progress_bar.setValue(0)
        self.worker.start()

    def _on_pause(self):
        if self.worker is not None:
            self.worker.request_pause()
            self.paused = True
            self._set_running(True)
            self.current_label.setText("已暂停，当前商品结束后挂起，点继续恢复…")

    def _on_resume(self):
        if self.worker is not None:
            self.worker.request_resume()
            self.paused = False
            self._set_running(True)
            self.current_label.setText("已继续，从暂停位置接着采集…")

    def _on_stop(self):
        if self.worker is not None:
            self.worker.request_stop()
            self.stop_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.current_label.setText("正在停止，将在当前商品结束后退出…")

    def _set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.scope_all.setEnabled(not running)
        self.scope_part.setEnabled(not running)
        self.limit_spin.setEnabled(not running and self.scope_part.isChecked())
        self.resume_check.setEnabled(not running)
        if not running:
            self.stop_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            return
        self.stop_btn.setEnabled(True)
        # 运行中暂停与继续互斥，暂停态下继续可用，运行态下暂停可用
        self.pause_btn.setEnabled(not self.paused)
        self.resume_btn.setEnabled(self.paused)

    # ---------- 进度事件 ----------
    def _on_progress(self, event: dict):
        etype = event.get("type")

        if etype == "start":
            self.total = event.get("total", 0)
            self.progress_bar.setRange(0, self.total)
            self.progress_bar.setFormat("%v / %m")
            self.progress_bar.setValue(0)
            self.current_label.setText("开始采集，共 %d 个商品" % self.total)

        elif etype == "item_start":
            self.progress_bar.setValue(event.get("index", 1) - 1)
            self.current_label.setText(
                "正在采集 %d/%d：%s %s %s %s"
                % (event.get("index"), event.get("total"),
                   event.get("door", ""), event.get("brand", ""),
                   event.get("name", ""), event.get("color", "")))

        elif etype == "item_done":
            self.progress_bar.setValue(event.get("index", 0))
            self.stat_success.set_value(event.get("success", 0))
            self.stat_failed.set_value(event.get("failed", 0))

        elif etype == "skip":
            self.progress_bar.setValue(event.get("index", 0))
            self.current_label.setText("跳过已完成 %d/%d：%s"
                                      % (event.get("index"), event.get("total"),
                                         event.get("name", "")))

        elif etype == "rest":
            self.current_label.setText("分批长休息约 %d 秒，模拟真人节奏…"
                                      % event.get("seconds", 0))

        elif etype == "login_failed":
            self.current_label.setText("登录态已失效，请重新登录后再采集。")

        elif etype == "captcha_pause":
            # 后端已自动暂停，这里更新按钮态并提醒用户手动处理
            self.paused = True
            self._set_running(True)
            self.current_label.setText("检测到页面验证弹窗，已暂停，等待人工处理。")
            QMessageBox.warning(
                self,
                "需要人工验证",
                "检测到页面验证弹窗，已自动暂停，不再继续点击。\n\n"
                "请在专用浏览器里手动完成验证，完成后点“继续”按钮恢复采集。\n"
                "依据：%s" % event.get("reason", ""))

        elif etype == "stopped":
            self.stat_success.set_value(event.get("success", 0))
            self.stat_failed.set_value(event.get("failed", 0))
            self.current_label.setText("已停止，进度已保存，可再次开始断点续跑。")

        elif etype == "finished":
            self.progress_bar.setValue(self.total)
            self.stat_success.set_value(event.get("success", 0))
            self.stat_failed.set_value(event.get("failed", 0))
            self.stat_review.set_value(event.get("review_count", 0))
            self.current_label.setText(
                "采集完成：成功 %d，失败 %d，待复核 %d。结果表已生成。"
                % (event.get("success", 0), event.get("failed", 0),
                   event.get("review_count", 0)))

    def _on_finished(self, summary: dict):
        self._set_running(False)
        stopped = bool(summary.get("stopped", False))
        if summary.get("error"):
            self.current_label.setText("采集异常：%s" % summary.get("error"))
        elif stopped:
            self.current_label.setText("已停止，进度已保存。")
        else:
            xlsx = summary.get("xlsx", "")
            if xlsx:
                self._append_log("结果表：%s" % xlsx)
        self.collect_finished.emit(stopped)

    # ---------- 日志 ----------
    def _append_log(self, text: str):
        self.log_view.appendPlainText(text)
        self.log_view.ensureCursorVisible()
