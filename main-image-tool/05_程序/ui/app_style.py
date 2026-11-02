# -*- coding: utf-8 -*-
"""统一的界面配色和样式表。"""

# 状态颜色
COLOR_OK = "#16a34a"        # 正常、已连接
COLOR_IDLE = "#9ca3af"      # 未连接、未开始
COLOR_WARN = "#d97706"      # 待确认、警告
COLOR_ERR = "#dc2626"       # 失败、异常
COLOR_PRIMARY = "#1f6feb"   # 主色调

# 主样式表
APP_QSS = """
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
                 "Hiragino Sans GB", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #f3f4f6;
}

QWidget#Card {
    background-color: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
}

/* 顶部环境区 */
QFrame#TopBar {
    background-color: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
}

QLabel#TopTitle {
    font-size: 15px;
    font-weight: 600;
    color: #111827;
}
QLabel#StateText {
    color: #374151;
}
QLabel#HintLabel {
    color: #6b7280;
}

/* 按钮 */
QPushButton {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 6px 16px;
    color: #374151;
}
QPushButton:hover {
    background-color: #f9fafb;
    border-color: #9ca3af;
}
QPushButton:pressed {
    background-color: #f3f4f6;
}
QPushButton:disabled {
    color: #9ca3af;
    background-color: #f3f4f6;
    border-color: #e5e7eb;
}

QPushButton#Primary {
    background-color: #1f6feb;
    border: 1px solid #1f6feb;
    color: #ffffff;
}
QPushButton#Primary:hover {
    background-color: #1a5fd0;
    border-color: #1a5fd0;
}
QPushButton#Primary:disabled {
    background-color: #9db8f0;
    border-color: #9db8f0;
    color: #eef2ff;
}

QPushButton#Danger {
    background-color: #ffffff;
    border: 1px solid #dc2626;
    color: #dc2626;
}
QPushButton#Danger:hover {
    background-color: #fef2f2;
}
QPushButton#Danger:disabled {
    color: #f3a4a4;
    border-color: #f3a4a4;
    background-color: #fef2f2;
}

/* 标签页 */
QTabWidget::pane {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    padding: 8px 22px;
    margin-right: 4px;
    color: #6b7280;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #1f6feb;
    border-bottom: 2px solid #1f6feb;
    background: #ffffff;
}
QTabBar::tab:hover:!selected {
    color: #374151;
}

/* 分组框 */
QGroupBox {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    background: #ffffff;
    font-weight: 600;
    color: #111827;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* 输入控件 */
QLineEdit, QComboBox, QSpinBox {
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 5px 8px;
    background: #ffffff;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #1f6feb;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    border: 1px solid #d1d5db;
    selection-background-color: #dbeafe;
    selection-color: #1f6feb;
    outline: none;
}

/* 进度条 */
QProgressBar {
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    background: #f3f4f6;
    text-align: center;
    height: 18px;
    color: #374151;
}
QProgressBar::chunk {
    background-color: #1f6feb;
    border-radius: 5px;
}

/* 表格 */
QTableView {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    gridline-color: #f0f1f3;
    background: #ffffff;
    selection-background-color: #dbeafe;
    selection-color: #111827;
    alternate-background-color: #f9fafb;
}
QHeaderView::section {
    background-color: #f9fafb;
    border: none;
    border-right: 1px solid #e5e7eb;
    border-bottom: 1px solid #e5e7eb;
    padding: 8px 10px;
    font-weight: 600;
    color: #374151;
}

/* 日志 */
QPlainTextEdit {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #1f2937;
    color: #e5e7eb;
    font-family: "Consolas", "Cascadia Mono", "Menlo", "Monaco",
                 "SF Mono", monospace;
    font-size: 12px;
}

/* 滚动条 */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #d1d5db;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #9ca3af;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #d1d5db;
    border-radius: 5px;
    min-width: 28px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* 状态栏 */
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #e5e7eb;
    color: #6b7280;
}
"""
