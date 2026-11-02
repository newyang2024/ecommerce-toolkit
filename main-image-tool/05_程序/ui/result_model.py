# -*- coding: utf-8 -*-
"""结果表格的数据模型和筛选代理。"""
from PyQt5.QtCore import QAbstractTableModel, QSortFilterProxyModel, Qt
from PyQt5.QtGui import QColor

from .app_style import COLOR_OK, COLOR_WARN, COLOR_IDLE
from .state_reader import STATUS_OK, STATUS_PENDING, STATUS_REVIEW

# 列定义：(字段 key, 列标题)
COLUMNS = [
    ("door", "门体"),
    ("brand", "品牌"),
    ("name", "简称"),
    ("url", "链接"),
    ("color", "颜色"),
    ("time", "活动时间"),
    ("price", "主图价格"),
    ("gift", "赠品"),
    ("guarantee", "保障权益"),
    ("redpacket", "红包"),
    ("other", "其他"),
    ("status", "状态"),
]

STATUS_COLOR = {
    STATUS_OK: QColor(COLOR_OK),
    STATUS_PENDING: QColor(COLOR_WARN),
    STATUS_REVIEW: QColor("#d94806"),
}


class ResultTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_at(self, row: int) -> dict:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return {}

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

        if role == Qt.ForegroundRole and key == "status":
            return STATUS_COLOR.get(row.get("status"), QColor(COLOR_IDLE))

        if role == Qt.ToolTipRole and key in ("gift", "guarantee",
                                              "redpacket", "other"):
            return row.get(key, "")
        return None


class ResultFilterProxy(QSortFilterProxyModel):
    """按品牌、门体、状态三个维度筛选。"""
    def __init__(self):
        super().__init__()
        self._brand = ""
        self._door = ""
        self._status = ""

    def set_filters(self, brand: str = "", door: str = "", status: str = ""):
        self._brand = brand
        self._door = door
        self._status = status
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        if model is None:
            return False
        row = model.row_at(source_row)

        if self._brand and row.get("brand") != self._brand:
            return False
        if self._door and self._door not in (row.get("door") or ""):
            return False
        if self._status and row.get("status") != self._status:
            return False
        return True
