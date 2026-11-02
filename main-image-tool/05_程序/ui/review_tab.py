# -*- coding: utf-8 -*-
"""复核清单标签页：展示待复核项，按原因筛选，只看不编辑。"""
from pathlib import Path

from PyQt5.QtCore import QAbstractTableModel, Qt
from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel,
                             QPushButton, QTableView, QVBoxLayout, QWidget)

from core.platform_utils import open_in_system
from .state_reader import (find_latest_result, find_latest_review,
                           parse_review_items)

# 列定义：(字段 key, 列标题, 初始宽度)
COLUMNS = [
    ("index", "序号", 55),
    ("name", "商品", 240),
    ("field", "字段", 90),
    ("issue", "复核原因", 180),
    ("detail", "当前值 / 详情", 320),
]


class ReviewTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._rows)

    def columnCount(self, parent=None):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section][1]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        key = COLUMNS[index.column()][0]
        if role == Qt.DisplayRole:
            return row.get(key, "")
        if role == Qt.ToolTipRole and key in ("name", "detail"):
            return str(row.get(key, ""))
        return None


class ReviewTab(QWidget):
    def __init__(self):
        super().__init__()
        self.model = ReviewTableModel()
        self.all_items = []
        self.review_path = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(12, 12, 12, 12)

        # 筛选栏
        top = QHBoxLayout()
        top.addWidget(QLabel("按原因筛选："))
        self.issue_box = QComboBox()
        self.issue_box.currentIndexChanged.connect(self._apply_filter)
        top.addWidget(self.issue_box)
        top.addStretch()
        self.count_label = QLabel("尚未加载复核清单")
        self.count_label.setObjectName("HintLabel")
        top.addWidget(self.count_label)
        root.addLayout(top)

        # 清单表格
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        for i, (_, _, w) in enumerate(COLUMNS):
            self.table.setColumnWidth(i, w)
        root.addWidget(self.table, 1)

        # 提示和按钮
        tip = QLabel("这些项请在导出的 Excel 中人工核对，本页面只展示、不编辑。")
        tip.setObjectName("HintLabel")
        root.addWidget(tip)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新清单")
        self.open_btn = QPushButton("打开复核清单（Markdown）")
        self.refresh_btn.clicked.connect(self.reload)
        self.open_btn.clicked.connect(self.open_markdown)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.open_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self.setLayout(root)

    def reload(self):
        """重新读取最新复核清单。"""
        result_path = find_latest_result()
        path = find_latest_review(result_path)
        if not path:
            self.count_label.setText("还没有复核清单，请先采集")
            self.all_items = []
            self.review_path = None
            self._rebuild_issue_box()
            return False

        self.review_path = path
        self.all_items = parse_review_items(path)
        self._rebuild_issue_box()
        return True

    def _rebuild_issue_box(self):
        """根据当前清单的原因类型重建筛选下拉。"""
        issues = []
        for it in self.all_items:
            if it["issue"] not in issues:
                issues.append(it["issue"])

        self.issue_box.blockSignals(True)
        self.issue_box.clear()
        self.issue_box.addItem("全部原因")
        for issue in issues:
            self.issue_box.addItem(issue)
        self.issue_box.blockSignals(False)
        self._apply_filter()

    def _apply_filter(self):
        target = self.issue_box.currentText()
        if not target or target == "全部原因":
            rows = self.all_items
        else:
            rows = [it for it in self.all_items if it["issue"] == target]
        self.model.set_rows(rows)
        self.count_label.setText(
            "显示 %d / %d 项，来源：%s" % (
                len(rows), len(self.all_items),
                Path(self.review_path).name if self.review_path else "无"))

    def open_markdown(self):
        """用系统默认程序打开最新复核清单 Markdown。"""
        if self.review_path and Path(self.review_path).exists():
            open_in_system(self.review_path)
        else:
            self.count_label.setText("还没有复核清单，请先采集")
