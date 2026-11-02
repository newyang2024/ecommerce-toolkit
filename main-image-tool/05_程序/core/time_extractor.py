# -*- coding: utf-8 -*-
"""活动时间提取：从文字块识别开始和结束时点，单个时点如实记录，不臆测。"""
import re
from dataclasses import dataclass
from typing import List, Optional

from .config_loader import load_rules
from .logger import get_logger
from .ocr_engine import TextBlock

logger = get_logger("time_extractor")


@dataclass
class TimeResult:
    raw: str
    start: str = ""
    end: str = ""
    need_review: bool = False


def _fmt(month: int, day: int, hour: int, year: Optional[int] = None) -> str:
    s = "%d月%d日%d点" % (month, day, hour)
    if year:
        s = "%d年" % year + s
    return s


class TimeExtractor:
    def __init__(self):
        tr = load_rules()["time"]
        self.rules = tr
        self.pats = {
            "full": re.compile(tr["full_range_pattern"]),
            "range": re.compile(tr["range_pattern"]),
            "same_day_hour": re.compile(tr["same_day_hour_pattern"]),
            "same_day": re.compile(tr["same_day_pattern"]),
            "today": re.compile(tr["today_pattern"]),
            "today_date": re.compile(tr["today_date_pattern"]),
            "date_only": re.compile(tr["date_only_pattern"]),
            "evening": re.compile(tr["evening_pattern"]),
            "single": re.compile(tr["single_pattern"]),
        }
        from datetime import datetime
        self.cur_month = datetime.now().month
        self.cur_year = datetime.now().year
        self.cur_day = datetime.now().day

    def _upcoming(self, day: int) -> bool:
        # 省略月份时，日期在今天或之后半个月内，补当前月是可靠的
        return self.cur_day <= day <= self.cur_day + 15

    def extract(self, blocks: List[TextBlock]) -> TimeResult:
        # 优先看带“活动时间”标签的块
        labeled = [b for b in blocks if "活动时间" in b.text]
        ordered = labeled + [b for b in blocks if b not in labeled]

        for b in ordered:
            t = b.text.replace(" ", "")

            m = self.pats["full"].search(t)
            if m:
                g = m.groups()
                sm, sd, sh = int(g[0]), int(g[1]), int(g[2])
                em, ed, eh = int(g[3]), int(g[4]), int(g[5])
                sy = ey = self.cur_year
                if em < sm:
                    ey = self.cur_year + 1
                return TimeResult(t, _fmt(sm, sd, sh, sy if em < sm else None),
                                  _fmt(em, ed, eh, ey if em < sm else None))

            m = self.pats["range"].search(t)
            if m:
                g = m.groups()
                sd, sh, ed, eh = int(g[0]), int(g[1]), int(g[2]), int(g[3])
                sm = em = self.cur_month
                return TimeResult(t, _fmt(sm, sd, sh), _fmt(em, ed, eh),
                                  need_review=not self._upcoming(sd))

            m = self.pats["same_day_hour"].search(t)
            if m:
                g = m.groups()
                d, h1, h2 = int(g[0]), int(g[1]), int(g[2])
                return TimeResult(t, _fmt(self.cur_month, d, h1),
                                  _fmt(self.cur_month, d, h2),
                                  need_review=not self._upcoming(d))

            m = self.pats["same_day"].search(t)
            if m:
                g = m.groups()
                d, h1, h2 = int(g[0]), int(g[1]), int(g[2])
                return TimeResult(t, _fmt(self.cur_month, d, h1),
                                  _fmt(self.cur_month, d, h2),
                                  need_review=not self._upcoming(d))

            m = self.pats["today"].search(t)
            if m:
                g = m.groups()
                h1, h2 = int(g[0]), int(g[1])
                return TimeResult(t, _fmt(self.cur_month, self.cur_day, h1),
                                  _fmt(self.cur_month, self.cur_day, h2))

            m = self.pats["today_date"].search(t)
            if m:
                d = "%d月%d日" % (self.cur_month, self.cur_day)
                return TimeResult(t, d, d)

            m = self.pats["date_only"].search(t)
            if m:
                g = m.groups()
                sm, sd, em, ed = int(g[0]), int(g[1]), int(g[2]), int(g[3])
                sy = ey = self.cur_year
                if em < sm:
                    ey = self.cur_year + 1
                return TimeResult(t, "%d月%d日" % (sm, sd), "%d月%d日" % (em, ed))

        # 兜底：带“晚”的时点，换算 24 小时
        for b in blocks:
            m = self.pats["evening"].search(b.text.replace(" ", ""))
            if m:
                d, h = int(m.group(1)), int(m.group(2))
                if h < 12:
                    h += 12
                return TimeResult(b.text, _fmt(self.cur_month, d, h), "",
                                  need_review=not self._upcoming(d))

        # 兜底：单个时点
        for b in blocks:
            m = self.pats["single"].search(b.text.replace(" ", ""))
            if m:
                d, h = int(m.group(1)), int(m.group(2))
                return TimeResult(b.text, _fmt(self.cur_month, d, h), "",
                                  need_review=not self._upcoming(d))

        return TimeResult("", need_review=True)
