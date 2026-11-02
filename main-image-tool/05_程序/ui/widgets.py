# -*- coding: utf-8 -*-
"""通用界面小组件：状态灯、信息统计卡。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout

from .app_style import COLOR_OK, COLOR_IDLE, COLOR_WARN, COLOR_ERR


class StatusDot(QLabel):
    """圆形状态灯，配合文字显示当前状态。"""

    def __init__(self, size: int = 12):
        super().__init__()
        self.setFixedSize(size, size)
        self.set_state("idle")

    def set_state(self, state: str):
        color = {
            "ok": COLOR_OK,
            "idle": COLOR_IDLE,
            "warn": COLOR_WARN,
            "err": COLOR_ERR,
        }.get(state, COLOR_IDLE)
        self.setStyleSheet(
            "background-color: %s; border-radius: %dpx;" % (color, self.width() // 2)
        )


class StateItem(QHBoxLayout):
    """状态灯加文字，用于顶部环境区。"""

    def __init__(self, title: str, default: str = "未检测"):
        super().__init__()
        self.dot = StatusDot()
        self.title = QLabel(title)
        self.text = QLabel(default)
        self.text.setObjectName("StateText")
        self.addWidget(self.dot)
        self.addWidget(self.title)
        self.addWidget(self.text)
        self.addStretch()
        self.setSpacing(8)

    def set_state(self, state: str, text: str):
        self.dot.set_state(state)
        self.text.setText(text)


class StatCard(QFrame):
    """统计数字卡片：标题加一个大数字。"""

    def __init__(self, title: str, value: str = "0", color: str = "#111827"):
        super().__init__()
        self.setObjectName("Card")
        self.setFixedHeight(78)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(
            "font-size: 24px; font-weight: 700; color: %s;" % color
        )
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #6b7280;")

        box = QVBoxLayout()
        box.setContentsMargins(16, 10, 16, 10)
        box.setSpacing(2)
        box.addWidget(self.value_label)
        box.addWidget(title_label)
        self.setLayout(box)

    def set_value(self, value: str, color: str = None):
        self.value_label.setText(str(value))
        if color:
            self.value_label.setStyleSheet(
                "font-size: 24px; font-weight: 700; color: %s;" % color
            )
