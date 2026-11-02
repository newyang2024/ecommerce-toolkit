# -*- coding: utf-8 -*-
"""结果回填：把每个商品的时间、价格、权益写回本地链接库副本，保留原格式。"""
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .config_loader import load_config, resolve_path
from .logger import get_logger

logger = get_logger("excel_writer")

# 列号：F时间 G价格 H赠品 I保障 J红包 K其他
COL_TIME = 6
COL_PRICE = 7
COL_GIFT = 8
COL_GUARANTEE = 9
COL_REDPACKET = 10
COL_OTHER = 11


class ExcelWriter:
    def __init__(self):
        self.config = load_config()
        self.src_path = resolve_path(self.config["paths"]["link_library"])
        result_dir = resolve_path(self.config["paths"]["result_dir"])
        prefix = self.config["output"]["result_file_prefix"]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.out_path = result_dir / ("%s_%s.xlsx" % (prefix, stamp))

    def write(self, results: List, lib) -> Path:
        import openpyxl
        from openpyxl.styles import Alignment

        wb = openpyxl.load_workbook(self.src_path)
        ws = wb.active
        wrap = Alignment(wrap_text=True, vertical="top")

        by_id = {r.item_id: r for r in results}
        filled = 0
        for item in lib.items:
            r = by_id.get(item.item_id)
            if not r:
                continue
            row = item.row
            ws.cell(row, COL_TIME, self._time_text(r)).alignment = wrap
            ws.cell(row, COL_PRICE, self._price_for(r, item)).alignment = wrap
            ws.cell(row, COL_GIFT, "\n".join(r.benefit.gift)).alignment = wrap
            ws.cell(row, COL_GUARANTEE, "\n".join(r.benefit.guarantee)).alignment = wrap
            ws.cell(row, COL_REDPACKET, "\n".join(r.benefit.redpacket)).alignment = wrap
            ws.cell(row, COL_OTHER, "\n".join(r.benefit.other)).alignment = wrap
            filled += 1

        self._autofit(ws, lib)

        wb.save(self.out_path)
        logger.info("结果已回填 %d 行，保存到 %s", filled, self.out_path)
        return self.out_path

    def _autofit(self, ws, lib):
        """结果表：数据列宽按内容自适应，行高按换行数自适应，保证文字全部露出。"""
        import math
        import unicodedata
        from openpyxl.utils import get_column_letter

        def disp_w(s):
            # 中文、全角按 2 个宽度，其余按 1
            return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
                       for ch in str(s))

        data_cols = list(range(COL_TIME, COL_OTHER + 1))
        max_col_w = 40  # 列宽上限，超过部分靠换行
        col_widths = {}
        for col in data_cols:
            maxw = 0
            for rr in range(3, ws.max_row + 1):
                v = ws.cell(rr, col).value
                if v:
                    for line in str(v).split("\n"):
                        maxw = max(maxw, disp_w(line))
            width = max(10, min(maxw + 2, max_col_w))
            col_widths[col] = width
            ws.column_dimensions[get_column_letter(col)].width = width

        line_h = 15  # 每行约 15 磅
        for rr in range(3, ws.max_row + 1):
            max_lines = 1
            for col in data_cols:
                v = ws.cell(rr, col).value
                if not v:
                    continue
                cw = col_widths[col]
                n = 0
                for line in str(v).split("\n"):
                    n += max(1, math.ceil(disp_w(line) / cw))
                max_lines = max(max_lines, n)
            ws.row_dimensions[rr].height = max(22, max_lines * line_h)

    def _time_text(self, r) -> str:
        if r.time.end:
            return "%s 到 %s" % (r.time.start, r.time.end)
        return r.time.start or ""

    def _price_for(self, r, item) -> str:
        if r.price.mode == "single":
            return r.price.single_price or ""
        if r.price.match_type == "door":
            key = self._door_key(item.door)
        else:
            key = item.color_group
        price = r.price.price_map.get(key)
        return price or "待确认"

    def _door_key(self, door: str) -> str:
        for d in ("十字", "法式", "对开", "三门"):
            if d in (door or ""):
                return d
        return door or ""
