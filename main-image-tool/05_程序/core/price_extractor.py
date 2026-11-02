# -*- coding: utf-8 -*-
"""价格提取：单一价格直接填，多价格按颜色或门型空间位置匹配，拿不准列候选。"""
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional,Tuple

from .config_loader import load_rules
from .link_library import normalize_color
from .logger import get_logger
from .ocr_engine import TextBlock

logger = get_logger("price_extractor")


@dataclass
class PriceResult:
    mode: str                       # single / multi / uncertain
    raw: str = ""
    match_type: str = ""            # color / door，多价格时按什么对应
    single_price: str = ""
    price_map: Dict[str, str] = field(default_factory=dict)  # 标签 -> 价格
    candidates: List[str] = field(default_factory=list)
    # 问号价格位置（活动未开始占位），坐标 x,y
    question_positions: List[Tuple[float, float]] = field(default_factory=list)
    need_review: bool = False


class PriceExtractor:
    def __init__(self):
        pr = load_rules()["price"]
        self.rules = pr
        self.price_pat = re.compile(pr["price_number_pattern"])
        self.repeated_pat = re.compile(pr["repeated_price_pattern"])
        self.min_price = pr["min_price"]
        self.max_price = pr["max_price"]
        self.rules_all = load_rules()

    def extract(self, blocks: List[TextBlock]) -> PriceResult:
        # found: (price, x, y, block)
        found: List[Tuple[int, float, float, TextBlock]] = []
        question_positions: List[Tuple[float, float]] = []
        for b in blocks:
            t = b.text.replace(" ", "")

            m = self.repeated_pat.fullmatch(t)
            if m:
                p1, p2 = int(m.group(1)), int(m.group(2))
                if self._valid(p1):
                    found.append((p1, b.cx - b.width / 4, b.cy, b))
                if p2 != p1 and self._valid(p2):
                    found.append((p2, b.cx + b.width / 4, b.cy, b))
                continue

            # 含问号的连写，如“？?992399”，前半是活动未开始的问号占位，
            # 后半是完整价格，按两半分别处理，避免完整价格被问号拖累
            if len(t) == 8 and ("？" in t or "?" in t):
                half = b.width / 2
                t1, t2 = t[:4], t[4:]
                if "？" in t1 or "?" in t1:
                    question_positions.append((b.cx - half / 2, b.cy))
                else:
                    mm = self.price_pat.fullmatch(t1)
                    if mm and self._valid(int(mm.group(1))):
                        found.append((int(mm.group(1)), b.cx - half / 2, b.cy, b))
                if "？" in t2 or "?" in t2:
                    question_positions.append((b.cx + half / 2, b.cy))
                else:
                    mm = self.price_pat.fullmatch(t2)
                    if mm and self._valid(int(mm.group(1))):
                        found.append((int(mm.group(1)), b.cx + half / 2, b.cy, b))
                continue

            m = self.price_pat.fullmatch(t)
            if m and self._valid(int(m.group(1))):
                found.append((int(m.group(1)), b.cx, b.cy, b))

        found = self._drop_context_noise(found, blocks)
        unique = sorted(set(p for p, _, _, _ in found))

        # 一个完整价格加一个问号位置：按颜色或门型标价，但问号那色活动未开始
        if len(unique) == 1 and question_positions:
            return self._match_partial(unique, found, question_positions, blocks)
        if len(unique) == 1:
            return PriceResult("single", single_price=str(unique[0]),
                               raw=self._raw_text(found))
        if len(unique) > 1:
            return self._match_multi(unique, found, blocks)
        if question_positions:
            return PriceResult("uncertain", candidates=[],
                               question_positions=question_positions,
                               need_review=True)
        return PriceResult("uncertain", candidates=[], need_review=True)

    def _valid(self, p: int) -> bool:
        return self.min_price <= p <= self.max_price

    def _drop_context_noise(self, found, blocks):
        # 排除带 L 的容量、年份徽章、尺寸、消费券，以及“满/消费/使用”语境里的数字
        year = datetime.now().year
        # 先收集尺寸数字，如“594mm超薄”，图上同数字的孤立标注也按尺寸排除
        size_nums = set()
        for b in blocks:
            t = b.text.replace(" ", "")
            for m in re.finditer(r"(\d{3,4})(?:mm|厘米|cm)", t):
                size_nums.add(int(m.group(1)))
            if "超薄" in t or "尺寸" in t:
                for m in re.finditer(r"(\d{3,4})", t):
                    size_nums.add(int(m.group(1)))

        out = []
        for p, x, y, b in found:
            if "L" in b.text or "l" in b.text:
                continue
            if p in size_nums:
                continue
            nearby = [xx.text for xx in blocks
                      if abs(xx.cy - y) < 80 and abs(xx.cx - x) < 220]
            joined = "".join(nearby)
            if any(k in joined for k in
                   ("满", "消费", "使用", "券", "mm", "超薄", "尺寸", "宽度")):
                continue
            # 年份徽章，如“2026 旗舰新品”，数字在当前年份附近且旁边有新品/旗舰/年
            if year - 2 <= p <= year + 1 and (
                    "新品" in joined or "旗舰" in joined or "年" in joined):
                continue
            out.append((p, x, y, b))
        return out

    def _door_label(self, text: str) -> Optional[str]:
        t = text.replace(" ", "")
        for door in self.rules.get("door_hints", []):
            if door in t:
                return door
        return None

    def _match_partial(self, unique, found, question_positions, blocks) -> PriceResult:
        # 一个完整价格加一个问号位置：按颜色或门型标价，问号那色活动未开始
        color_labels, door_labels = self._collect_labels(blocks)
        if color_labels:
            labels, match_type = color_labels, "color"
        elif door_labels:
            labels, match_type = door_labels, "door"
        else:
            labels, match_type = [], ""

        price_map: Dict[str, str] = {}
        for p, x, y, pb in found:
            best = self._nearest_label(x, y, labels)
            if best:
                price_map[best] = str(p)

        if labels and price_map:
            return PriceResult("multi", match_type=match_type,
                               price_map=price_map,
                               question_positions=question_positions,
                               raw=self._raw_text(found), need_review=True)

        return PriceResult("uncertain", candidates=[str(x) for x in unique],
                           question_positions=question_positions,
                           raw=self._raw_text(found), need_review=True)

    def _collect_labels(self, blocks):
        color_labels = []
        for b in blocks:
            g = normalize_color(b.text, self.rules_all)
            if g in ("白", "灰") and len(b.text.replace(" ", "")) <= 5:
                color_labels.append((g, b))
        door_labels = []
        for b in blocks:
            d = self._door_label(b.text)
            if d and len(b.text.replace(" ", "")) <= 8:
                door_labels.append((d, b))
        return color_labels, door_labels

    def _match_multi(self, unique, found, blocks) -> PriceResult:
        color_labels, door_labels = self._collect_labels(blocks)

        if color_labels:
            labels, match_type = color_labels, "color"
        elif door_labels:
            labels, match_type = door_labels, "door"
        else:
            labels, match_type = [], ""

        price_map: Dict[str, str] = {}
        for p, x, y, pb in found:
            best = self._nearest_label(x, y, labels)
            if best:
                price_map[best] = str(p)

        # 双色兜底：两个价格只匹配到一个颜色，另一个价格上方有款式标签，
        # 这种款式名（如机皇2.0）没有颜色词，按白灰互补推断，仍标记人工复核
        if match_type == "color" and len(unique) == 2 and len(price_map) == 1:
            matched_color = next(iter(price_map))
            other_color = "灰" if matched_color == "白" else "白"
            for p, x, y, pb in found:
                if str(p) in price_map.values():
                    continue
                if self._has_above_label(x, y, blocks):
                    price_map[other_color] = str(p)
            if len(price_map) == 2:
                return PriceResult("multi", match_type=match_type,
                                   price_map=price_map,
                                   raw=self._raw_text(found), need_review=True)

        if labels and price_map and len(price_map) == len(set(price_map.values())):
            return PriceResult("multi", match_type=match_type,
                               price_map=price_map, raw=self._raw_text(found))

        return PriceResult("uncertain", candidates=[str(x) for x in unique],
                           raw=self._raw_text(found), need_review=True)

    def _nearest_label(self, x: float, y: float, labels) -> Optional[str]:
        best = None
        best_d = 1e9
        for g, cb in labels:
            if cb.cy > y:
                continue
            dx = abs(cb.cx - x)
            dy = y - cb.cy
            if dx < 200:
                d = dx + dy
                if d < best_d:
                    best = g
                    best_d = d
        return best

    def _has_above_label(self, x: float, y: float, blocks) -> bool:
        for b in blocks:
            t = b.text.replace(" ", "")
            if not t or len(t) > 6:
                continue
            if b.cy >= y:
                continue
            if abs(b.cx - x) < 100 and y - b.cy < 60:
                return True
        return False

    def _raw_text(self, found) -> str:
        return "；".join(sorted(set("%s" % p for p, _, _, _ in found)))
