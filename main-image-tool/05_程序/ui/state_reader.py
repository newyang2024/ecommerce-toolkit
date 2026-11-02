# -*- coding: utf-8 -*-
"""读取结果 Excel 和复核清单，展开成表格行，供结果表格使用。"""
import re
from pathlib import Path
from typing import Dict, List, Optional

from core.config_loader import load_config, resolve_path

# 结果表列号（1-based）
COL_DOOR = 1
COL_BRAND = 2
COL_NAME = 3
COL_URL = 4
COL_COLOR = 5
COL_TIME = 6
COL_PRICE = 7
COL_GIFT = 8
COL_GUARANTEE = 9
COL_REDPACKET = 10
COL_OTHER = 11

DATA_START_ROW = 3

RESULT_PREFIX = "竞对主图识别结果"
REVIEW_PREFIX = "人工复核清单"

STATUS_OK = "已确定"
STATUS_PENDING = "待确认"
STATUS_REVIEW = "待复核"


def get_result_dir() -> Path:
    return resolve_path(load_config()["paths"]["result_dir"])


def find_latest_result() -> Optional[Path]:
    """定位当前结果文件。优先读 latest_result 指针，否则选内容最完整的结果
    （已确定价格数最多，其次数据行数最多，再其次时间最新）。"""
    d = get_result_dir()
    pointer = d / "latest_result.txt"
    if pointer.exists():
        try:
            p = Path(pointer.read_text(encoding="utf-8").strip())
            if p.exists():
                return p
        except Exception:
            pass

    best = None
    best_score = (-1, -1, 0.0)
    for p in d.glob("%s_*.xlsx" % RESULT_PREFIX):
        total, ok = _count_data_rows(p)
        score = (ok, total, p.stat().st_mtime)
        if score > best_score:
            best_score = score
            best = p
    return best


def find_latest_review(result_path: Optional[Path] = None) -> Optional[Path]:
    """定位复核清单。优先找与结果文件同时间戳的，否则取最新一个。"""
    d = get_result_dir()
    if result_path is not None:
        stamp = _timestamp_of(result_path.name)
        if stamp:
            sibling = d / ("%s_%s.md" % (REVIEW_PREFIX, stamp))
            if sibling.exists():
                return sibling
    files = sorted(d.glob("%s_*.md" % REVIEW_PREFIX))
    return files[-1] if files else None


def _timestamp_of(name: str) -> str:
    m = re.search(r"_(\d{8}_\d{6})", name)
    return m.group(1) if m else ""


def parse_review_map(md_path: Path) -> Dict[str, str]:
    """解析复核清单，返回 item_id 到问题描述的映射。"""
    text = md_path.read_text(encoding="utf-8")
    mapping = {}
    cur_id = None
    for line in text.splitlines():
        m = re.search(r"（(\d+)）\s*$", line)
        if m:
            cur_id = m.group(1)
        elif cur_id and line.strip().startswith("- 问题："):
            mapping[cur_id] = line.strip()[len("- 问题："):]
            cur_id = None
    return mapping


def parse_review_items(md_path: Path) -> List[dict]:
    """解析复核清单，返回完整条目列表：序号、名称、item_id、字段、问题、详情。"""
    text = md_path.read_text(encoding="utf-8")
    items = []
    cur = None
    for line in text.splitlines():
        head = re.match(r"^(\d+)\.\s+(.+)（(\d+)）\s*$", line)
        if head:
            if cur:
                items.append(cur)
            cur = {
                "index": int(head.group(1)),
                "name": head.group(2).strip(),
                "item_id": head.group(3),
                "field": "",
                "issue": "",
                "detail": "",
            }
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("- 字段："):
            cur["field"] = s[len("- 字段："):]
        elif s.startswith("- 问题："):
            cur["issue"] = s[len("- 问题："):]
        elif s.startswith("- 详情："):
            cur["detail"] = s[len("- 详情："):]
    if cur:
        items.append(cur)
    return items


def read_result_rows(xlsx_path: Path,
                     review_map: Optional[Dict[str, str]] = None) -> List[dict]:
    """读结果 Excel，展开成一行一个 dict 的列表。"""
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.active
    review_map = review_map or {}

    # 门体列是合并单元格，向下填充，避免只有每组第一行有门体
    door_fill = {}
    for mr in ws.merged_cells.ranges:
        if mr.min_col == COL_DOOR and mr.max_col == COL_DOOR:
            top_val = ws.cell(mr.min_row, COL_DOOR).value
            for rr in range(mr.min_row, mr.max_row + 1):
                door_fill[rr] = top_val

    rows = []
    for r in range(DATA_START_ROW, ws.max_row + 1):
        brand = _cell(ws, r, COL_BRAND)
        name = _cell(ws, r, COL_NAME)
        if not (brand or name):
            continue

        door = door_fill.get(r, _cell(ws, r, COL_DOOR))
        price = _cell(ws, r, COL_PRICE)
        url = _cell(ws, r, COL_URL)
        item_id = extract_item_id(url)
        issue = review_map.get(item_id, "")
        status = infer_status(price, issue)

        rows.append({
            "item_id": item_id,
            "door": door or "",
            "brand": brand or "",
            "name": name or "",
            "url": url,
            "color": _cell(ws, r, COL_COLOR),
            "time": _cell(ws, r, COL_TIME),
            "price": price,
            "gift": _cell(ws, r, COL_GIFT),
            "guarantee": _cell(ws, r, COL_GUARANTEE),
            "redpacket": _cell(ws, r, COL_REDPACKET),
            "other": _cell(ws, r, COL_OTHER),
            "status": status,
            "review_issue": issue,
        })
    wb.close()
    return rows


def infer_status(price: str, review_issue: str) -> str:
    p = (price or "").strip()
    if not p or p == "待确认":
        return STATUS_PENDING
    if review_issue and "推断" in review_issue:
        return STATUS_REVIEW
    return STATUS_OK


def extract_item_id(url: str) -> str:
    if not url:
        return ""
    m = re.search(r"[?&]id=(\d+)", url)
    return m.group(1) if m else ""


def _cell(ws, row: int, col: int) -> str:
    v = ws.cell(row, col).value
    if v is None:
        return ""
    return str(v).strip()


def _count_data_rows(xlsx_path: Path):
    """返回 (数据行数, 已确定价格行数)，用于判断哪个结果文件最完整。"""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(xlsx_path, read_only=True)
        ws = wb.active
        total = 0
        ok = 0
        for r in ws.iter_rows(min_row=DATA_START_ROW, min_col=COL_BRAND,
                              max_col=COL_PRICE, values_only=True):
            brand = r[0]
            name = r[1]
            if not (brand or name):
                continue
            total += 1
            price = r[COL_PRICE - COL_BRAND]
            ptext = str(price).strip() if price is not None else ""
            if ptext and ptext != "待确认" and ptext.isdigit():
                ok += 1
        wb.close()
        return total, ok
    except Exception:
        return 0, 0
