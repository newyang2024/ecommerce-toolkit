# -*- coding: utf-8 -*-
"""链接库读取：解析本地 Excel，按商品 id 聚合，减少重复打开页面。"""
import re
from dataclasses import dataclass, field
from typing import Dict, List

from .config_loader import load_config, resolve_path
from .logger import get_logger

logger = get_logger("link_library")


@dataclass
class ProductItem:
    row: int                  # 链接库行号
    door: str                  # 门体
    brand: str                 # 品牌
    name: str                  # 简称
    url: str                   # 链接
    item_id: str               # 商品 id
    color_raw: str             # 颜色原文
    color_group: str = ""      # 归并后色系：白/灰/待确认
    is_aggregate: bool = False  # 是否聚合（同一 id 多行）


def _extract_item_id(url: str) -> str:
    m = re.search(r"[?&]id=(\d+)", url or "")
    return m.group(1) if m else ""


def normalize_color(color_raw: str, rules: dict) -> str:
    """颜色归并到白、灰，无法明确的标记待确认。"""
    c = (color_raw or "").strip()
    color_rules = rules.get("color", {})

    # 待确认项优先
    for p in color_rules.get("pending", []):
        if p in c:
            return "待确认"

    # 直接映射
    name_map = color_rules.get("name_map", {})
    for k, v in name_map.items():
        if k in c:
            return v

    # 关键词
    for w in color_rules.get("white_keywords", []):
        if w in c:
            return "白"
    for w in color_rules.get("gray_keywords", []):
        if w in c:
            return "灰"

    return "待确认"


class LinkLibrary:
    def __init__(self):
        self.config = load_config()
        self.items: List[ProductItem] = []
        self._id_rows: Dict[str, List[ProductItem]] = {}

    def load(self) -> List[ProductItem]:
        import openpyxl

        path = resolve_path(self.config["paths"]["link_library"])
        if not path.exists():
            raise FileNotFoundError("找不到链接库: %s" % path)

        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active

        rules = self._load_rules()
        door = None
        for r in range(3, ws.max_row + 1):
            d = ws.cell(r, 1).value
            if d:
                door = d
            url = ws.cell(r, 4).value
            if not url or "detail.tmall.com" not in url:
                continue
            item = ProductItem(
                row=r,
                door=door,
                brand=ws.cell(r, 2).value,
                name=ws.cell(r, 3).value,
                url=url,
                item_id=_extract_item_id(url),
                color_raw=ws.cell(r, 5).value or "",
            )
            item.color_group = normalize_color(item.color_raw, rules)
            self.items.append(item)

        # 按商品 id 聚合
        self._id_rows = {}
        for item in self.items:
            self._id_rows.setdefault(item.item_id, []).append(item)
        for item in self.items:
            item.is_aggregate = len(self._id_rows[item.item_id]) > 1

        logger.info("链接库读取完成：%d 行，%d 个唯一商品，聚合商品 %d 个",
                    len(self.items), len(self._id_rows),
                    sum(1 for v in self._id_rows.values() if len(v) > 1))
        return self.items

    def _load_rules(self) -> dict:
        from .config_loader import load_rules
        return load_rules()

    def unique_tasks(self) -> List[ProductItem]:
        """按商品 id 去重后的采集任务，每个 id 只打开一次。"""
        seen = set()
        tasks = []
        for item in self.items:
            if item.item_id not in seen:
                seen.add(item.item_id)
                tasks.append(item)
        return tasks

    def rows_of(self, item_id: str) -> List[ProductItem]:
        """同一商品 id 对应的所有行，用于一次识别后回填多行。"""
        return self._id_rows.get(item_id, [])
