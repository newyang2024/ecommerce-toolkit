# -*- coding: utf-8 -*-
"""人工复核清单：收集时间、价格、权益里拿不准或缺失的项，输出 Markdown。"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from .config_loader import load_config, resolve_path
from .logger import get_logger

logger = get_logger("review")


@dataclass
class ReviewItem:
    item_id: str
    name: str
    field: str
    issue: str
    detail: str


class ReviewCollector:
    def __init__(self):
        self.config = load_config()

    def collect(self, results: List, lib) -> List[ReviewItem]:
        items = []
        name_of = {t.item_id: t.name for t in lib.unique_tasks()}
        for r in results:
            item_id = r.item_id
            name = name_of.get(item_id, item_id)

            if not r.time.start:
                items.append(ReviewItem(item_id, name, "活动时间",
                                        "未识别到时间", "图上没找到可识别的时间"))
            elif r.time.need_review:
                items.append(ReviewItem(item_id, name, "活动时间",
                                        "时间省略月份或为单时点",
                                        "原文：%s" % r.time.raw))

            if r.price.mode == "uncertain":
                items.append(ReviewItem(item_id, name, "主图价格",
                                        "价格无法唯一确定",
                                        "候选：%s" % "、".join(r.price.candidates)))
            elif r.price.mode == "single" and not r.price.single_price:
                items.append(ReviewItem(item_id, name, "主图价格",
                                        "未识别到价格", "图上没找到合理价格"))
            elif r.price.mode == "multi":
                if r.price.match_type == "door":
                    keys = {self._door_key(x.door) for x in lib.rows_of(item_id)}
                else:
                    keys = {x.color_group for x in lib.rows_of(item_id)}
                keys = {k for k in keys if k and k != "待确认"}
                if not all(k in r.price.price_map for k in keys):
                    items.append(ReviewItem(item_id, name, "主图价格",
                                            "多价格标签对不上",
                                            "标签价：%s" % r.price.price_map))
                elif r.price.need_review:
                    items.append(ReviewItem(item_id, name, "主图价格",
                                            "多价格含推断，建议核对",
                                            "标签价：%s" % r.price.price_map))

            if not any((r.benefit.gift, r.benefit.guarantee,
                        r.benefit.redpacket, r.benefit.other)):
                items.append(ReviewItem(item_id, name, "主图权益",
                                        "四类权益都为空", "图上没识别到权益"))
        return items

    def _door_key(self, door: str) -> str:
        for d in ("十字", "法式", "对开", "三门"):
            if d in (door or ""):
                return d
        return door or ""

    def write_markdown(self, items: List[ReviewItem]) -> Path:
        result_dir = resolve_path(self.config["paths"]["result_dir"])
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = result_dir / ("人工复核清单_%s.md" % stamp)

        lines = ["# 人工复核清单", "", "共 %d 项需要人工核对。" % len(items), ""]
        for i, it in enumerate(items, 1):
            lines.append("%d. %s（%s）" % (i, it.name, it.item_id))
            lines.append("   - 字段：%s" % it.field)
            lines.append("   - 问题：%s" % it.issue)
            lines.append("   - 详情：%s" % it.detail)
            lines.append("")
        out.write_text("\n".join(lines), encoding="utf-8")
        logger.info("人工复核清单 %d 项，保存到 %s", len(items), out)
        return out
