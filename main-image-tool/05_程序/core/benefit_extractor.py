# -*- coding: utf-8 -*-
"""权益提取：四分层，保留原文，去重，不重复归类，支持两张图合并。"""
from dataclasses import dataclass, field
from typing import List, Optional, Union

from .config_loader import load_rules
from .logger import get_logger
from .ocr_engine import TextBlock

logger = get_logger("benefit_extractor")

# 纯标签块，单独出现时不是权益内容
LABEL_WORDS = {"红包", "赠品", "权益", "保障", "好礼", "活动权益", "其他"}

# 各类别核心权益点：核心点名称到识别词，用于把不同说法合并
CORE_POINTS = {
    "guarantee": [
        ("压缩机包换", ["压缩机", "包换"]),
        ("价保", ["价保"]),
        ("买贵", ["买贵"]),
        ("送货入户", ["送货入户"]),
        ("保修", ["保修"]),
        ("运费险", ["运费险"]),
    ],
    "gift": [
        ("烤箱", ["烤箱"]),
        ("皮肤贴", ["皮肤贴"]),
        ("制冰", ["制冰"]),
        ("汤锅", ["汤锅"]),
        ("文创礼包", ["文创大礼包"]),
        ("托特包", ["托特包"]),
    ],
    "redpacket": [
        ("瓜分", ["瓜分"]),
        ("返红包", ["红包"]),
        ("返现", ["返现", "返20", "返50", "返100", "返200"]),
    ],
    "other": [
        ("补贴", ["补贴"]),
        ("套购", ["套购"]),
        ("免息", ["免息"]),
        ("85折", ["85折"]),
        ("95折", ["95折"]),
        ("97折", ["97折"]),
        ("立减", ["立减"]),
    ],
}


@dataclass
class BenefitResult:
    gift: List[str] = field(default_factory=list)
    guarantee: List[str] = field(default_factory=list)
    redpacket: List[str] = field(default_factory=list)
    other: List[str] = field(default_factory=list)
    need_review: bool = False


class BenefitExtractor:
    def __init__(self):
        b = load_rules()["benefit"]
        self.benefit = b
        self.noise = b.get("noise", [])
        self.gift_lead = b.get("gift_lead", [])
        self.gift_items = b["gift"].get("item_keywords", [])
        self.gift_actions = b["gift"].get("action_keywords", [])
        self.guarantee_kw = b["guarantee"]["keywords"]
        self.redpacket_kw = b["redpacket"]["keywords"]
        self.other_kw = b["other"]["keywords"]

    def extract(self, blocks_list: Union[List[TextBlock], List[List[TextBlock]]]
                ) -> BenefitResult:
        if blocks_list and isinstance(blocks_list[0], TextBlock):
            groups = [blocks_list]
        else:
            groups = blocks_list

        result = BenefitResult()
        seen = set()
        for blocks in groups:
            for b in blocks:
                cat = self._classify(b.text)
                if not cat:
                    continue
                item = self._clean(b.text)
                key = self._norm(item)
                if key in seen:
                    continue
                seen.add(key)
                getattr(result, cat).append(item)

        for cat in ("gift", "guarantee", "redpacket", "other"):
            setattr(result, cat, self._merge(cat, getattr(result, cat)))

        logger.info("权益提取：赠品%d 保障%d 红包%d 其他%d",
                    len(result.gift), len(result.guarantee),
                    len(result.redpacket), len(result.other))
        return result

    def _merge(self, cat: str, items: List[str]) -> List[str]:
        points = CORE_POINTS.get(cat, [])
        tagged = []
        for it in items:
            t = self._norm(it)
            hits = {name for name, words in points
                    if all(w in t for w in words)}
            tagged.append((it, hits))
        tagged.sort(key=lambda x: (-len(x[1]), -len(x[0])))

        kept, covered = [], set()
        for it, hits in tagged:
            if hits and hits.issubset(covered):
                continue
            kept.append(it)
            covered |= hits
        return kept

    def _classify(self, text: str) -> Optional[str]:
        t = text.replace(" ", "")
        if len(t) <= 1 or t in LABEL_WORDS:
            return None
        # 价格计算式，如（活动价-消费券-补贴）×85折
        if "×" in t and ("-" in t or "（" in t or "(" in t or "折" in t):
            return None

        # 保障优先，含运费险等
        if self._hit(self.guarantee_kw, t):
            return "guarantee"

        # 赠品：有具体赠品
        if self._hit(self.gift_items, t):
            return "gift"
        # 只有赠品动作
        if self._hit(self.gift_actions, t):
            if self._hit(self.gift_lead, t):
                return None
            return "gift"

        # 纯引导语
        if self._hit(self.noise, t):
            return None

        if self._hit(self.redpacket_kw, t):
            return "redpacket"
        if self._hit(self.other_kw, t):
            return "other"
        return None

    def _hit(self, keywords, t) -> bool:
        return any(kw in t for kw in keywords)

    def _clean(self, text: str) -> str:
        import re
        t = text.strip()
        for lead in ("*", "活动时间：", "活动时间:"):
            if t.startswith(lead):
                t = t[len(lead):]
        # 去掉结尾引导语，如"立即抢购>"
        t = re.sub(r"[！!0]?\s*立即抢购[>》]?\s*$", "", t)
        # 去掉开头引导语，如"双11优惠开抢！"
        t = re.sub(r"^双1{1,2}优惠开抢[！!]?\s*", "", t)
        return t

    def _norm(self, text: str) -> str:
        import re
        return re.sub(r"[\s，。、；：:（）()]", "", text)
