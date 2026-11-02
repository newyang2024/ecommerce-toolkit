# -*- coding: utf-8 -*-
"""结果查看标签页：筛选、结果表格、导出。"""
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
                             QLabel, QPushButton, QTableView, QVBoxLayout,
                             QWidget)

from core.platform_utils import open_in_system
from .result_model import COLUMNS, ResultFilterProxy, ResultTableModel
from .state_reader import (find_latest_result, find_latest_review,
                           get_result_dir, parse_review_map, read_result_rows)

BRAND_OPTIONS = ["", "美的", "海尔"]
BRAND_LABELS = ["全部品牌", "美的", "海尔"]
DOOR_OPTIONS = ["", "十字", "法式", "对开", "三门", "小冰箱"]
DOOR_LABELS = ["全部门体", "十字", "法式", "对开", "三门", "小冰箱"]
STATUS_OPTIONS = ["", "已确定", "待确认", "待复核"]
STATUS_LABELS = ["全部状态", "已确定", "待确认", "待复核"]

# 各列初始宽度
COL_WIDTHS = [60, 55, 150, 50, 95, 150, 90, 165, 185, 130, 185, 75]


class ResultTab(QWidget):
    def __init__(self):
        super().__init__()
        self.source_model = ResultTableModel()
        self.proxy = ResultFilterProxy()
        self.proxy.setSourceModel(self.source_model)
        self.proxy.setSortRole(Qt.DisplayRole)

        self.current_path = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(12, 12, 12, 12)

        # 筛选栏
        filter_row = QHBoxLayout()
        self.brand_box = QComboBox()
        self.door_box = QComboBox()
        self.status_box = QComboBox()
        for label in BRAND_LABELS:
            self.brand_box.addItem(label)
        for label in DOOR_LABELS:
            self.door_box.addItem(label)
        for label in STATUS_LABELS:
            self.status_box.addItem(label)

        self.brand_box.currentIndexChanged.connect(self._apply_filter)
        self.door_box.currentIndexChanged.connect(self._apply_filter)
        self.status_box.currentIndexChanged.connect(self._apply_filter)

        filter_row.addWidget(QLabel("筛选："))
        filter_row.addWidget(self.brand_box)
        filter_row.addWidget(self.door_box)
        filter_row.addWidget(self.status_box)
        filter_row.addStretch()
        self.count_label = QLabel("尚未加载结果")
        self.count_label.setObjectName("HintLabel")
        filter_row.addWidget(self.count_label)
        root.addLayout(filter_row)

        # 结果表格
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for i, w in enumerate(COL_WIDTHS):
            self.table.setColumnWidth(i, w)
            header.setSectionResizeMode(i, QHeaderView.Interactive)
        root.addWidget(self.table, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新结果")
        self.export_btn = QPushButton("导出 Excel")
        self.open_dir_btn = QPushButton("打开结果所在文件夹")
        self.refresh_btn.clicked.connect(self.reload)
        self.export_btn.clicked.connect(self.export)
        self.open_dir_btn.clicked.connect(self.open_folder)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addWidget(self.open_dir_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self.setLayout(root)

    def reload(self):
        """重新读取最新结果文件并刷新表格。"""
        path = find_latest_result()
        if not path:
            self.count_label.setText("还没有结果文件，请先采集")
            self.source_model.set_rows([])
            self.current_path = None
            return False

        review_path = find_latest_review(path)
        review_map = {}
        if review_path:
            review_map = parse_review_map(review_path)

        rows = read_result_rows(path, review_map)
        self.source_model.set_rows(rows)
        self.current_path = path
        self._update_count()
        return True

    def _apply_filter(self):
        brand = BRAND_OPTIONS[self.brand_box.currentIndex()]
        door = DOOR_OPTIONS[self.door_box.currentIndex()]
        status = STATUS_OPTIONS[self.status_box.currentIndex()]
        self.proxy.set_filters(brand=brand, door=door, status=status)
        self._update_count()

    def _update_count(self):
        total = self.source_model.rowCount()
        shown = self.proxy.rowCount()
        if self.current_path:
            self.count_label.setText(
                "显示 %d / %d 行，来源：%s" % (
                    shown, total, Path(self.current_path).name))
        else:
            self.count_label.setText("显示 %d / %d 行" % (shown, total))

    def export(self):
        """把当前筛选后可见的行导出成新 Excel。"""
        if self.proxy.rowCount() == 0:
            self.count_label.setText("当前没有可导出的行")
            return

        default_name = "主图识别结果_筛选导出.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出当前筛选结果",
            str(get_result_dir() / default_name), "Excel 文件 (*.xlsx)")
        if not path:
            return

        rows = []
        for r in range(self.proxy.rowCount()):
            source_row = self.proxy.mapToSource(self.proxy.index(r, 0)).row()
            rows.append(self.source_model.row_at(source_row))
        try:
            self._write_export(rows, path)
            self.count_label.setText("已导出 %d 行到：%s" % (len(rows), path))
        except Exception as e:
            self.count_label.setText("导出失败：%s" % e)

    def _write_export(self, rows, path):
        import math
        import unicodedata

        import openpyxl
        from openpyxl.styles import Alignment, Font
        from openpyxl.utils import get_column_letter

        def disp_w(s):
            # 中文、全角按 2 个宽度，其余按 1，与正式结果表口径一致
            return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
                       for ch in str(s))

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append([c[1] for c in COLUMNS])
        for cell in ws[1]:
            cell.font = Font(bold=True)

        wrap = Alignment(wrap_text=True, vertical="top")
        for row in rows:
            ws.append([row.get(c[0], "") for c in COLUMNS])
        for r in ws.iter_rows(min_row=2):
            for cell in r:
                cell.alignment = wrap

        # 列宽自适应；链接列默认隐藏但数据保留，取消隐藏即可看到
        max_col_w = 40
        col_widths = {}
        for idx, c in enumerate(COLUMNS, start=1):
            letter = get_column_letter(idx)
            if c[0] == "url":
                ws.column_dimensions[letter].width = 55
                ws.column_dimensions[letter].hidden = True
                col_widths[idx] = 55
                continue
            maxw = 0
            for rr in range(1, ws.max_row + 1):
                v = ws.cell(rr, idx).value
                if v:
                    for line in str(v).split("\n"):
                        maxw = max(maxw, disp_w(line))
            width = max(10, min(maxw + 2, max_col_w))
            col_widths[idx] = width
            ws.column_dimensions[letter].width = width

        # 行高按换行数自适应，保证文字全部露出
        for rr in range(2, ws.max_row + 1):
            max_lines = 1
            for idx, c in enumerate(COLUMNS, start=1):
                if c[0] == "url":
                    continue
                v = ws.cell(rr, idx).value
                if not v:
                    continue
                cw = col_widths[idx]
                n = 0
                for line in str(v).split("\n"):
                    n += max(1, math.ceil(disp_w(line) / cw))
                max_lines = max(max_lines, n)
            ws.row_dimensions[rr].height = max(22, max_lines * 15)

        wb.save(path)

    def open_folder(self):
        """打开结果所在文件夹，并选中当前结果文件。"""
        target = self.current_path
        if target and Path(target).exists():
            open_in_system(Path(target).parent)
        else:
            open_in_system(get_result_dir())
