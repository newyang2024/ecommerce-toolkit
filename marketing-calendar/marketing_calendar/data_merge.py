"""将五份已下载 CSV 写入大型现有工作簿的三张源表。

目标工作簿超过百 MB，完整对象模型导入在低内存电脑上不可用；因此仅流式
替换三张源表的 sheetData。其余 ZIP 成员逐字节复制，原文件始终不修改。
"""

from __future__ import annotations

import csv
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import BinaryIO, Callable, Iterator
from uuid import uuid4
from zipfile import ZipFile


class MergeError(RuntimeError):
    """输入结构、列映射或输出校验不满足安全合并条件。"""


SOURCE_SHEETS = {"subject": 12, "keyword": 13, "audience": 14}
START_COLUMNS = {"subject": 12, "keyword": 11, "audience": 10}
MAX_COLUMNS = {"subject": 100, "keyword": 87, "audience": 84}
EXTRA_HEADERS = (
    "平台补贴金额",
    "补贴引导成交金额",
    "发券补贴商品个数",
    "补贴引导成交人数",
)
REPORT_PREFIXES = {
    "product": "商品报表",
    "plan": "计划报表",
    "content": "内容报表",
    "audience": "人群报表",
    "keyword": "关键词报表",
}
SUBJECT_ORDER = ("product", "plan", "content")
EXCEL_EPOCH = date(1899, 12, 30)
_NUMERIC = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_CELL_REFERENCE = re.compile(r"([A-Z]+)([0-9]+)\Z")


@dataclass(frozen=True)
class SourceAudit:
    report_key: str
    path: Path
    headers: tuple[str, ...]
    row_count: int
    first_date: date
    last_date: date


@dataclass(frozen=True)
class MergePlan:
    template: Path
    output: Path
    audits: dict[str, SourceAudit]
    headers: dict[str, dict[str, int]]
    row_counts: dict[str, int]


def prepare_merge(
    template: Path,
    csv_directory: Path,
    output: Path,
    *,
    expected_start: date,
    expected_end: date,
) -> MergePlan:
    if expected_start > expected_end:
        raise MergeError("开始日期不能晚于结束日期")
    if not template.is_file():
        raise MergeError(f"目标工作簿不存在：{template}")
    if output.exists() or output.resolve() == template.resolve():
        raise MergeError(f"输出已存在或与原文件相同，拒绝覆盖：{output}")
    audits: dict[str, SourceAudit] = {}
    for key, prefix in REPORT_PREFIXES.items():
        matches = tuple(csv_directory.glob(f"{prefix}*.csv"))
        if len(matches) != 1:
            raise MergeError(f"{key} CSV 需要恰好一份，实际 {len(matches)} 份")
        audits[key] = _audit_csv(key, matches[0], expected_start, expected_end)

    with ZipFile(template) as source:
        # 匹配源改为底本内维护，避免选择了不完整工作簿却悄悄输出无匹配源的结果。
        from .matching_source import _sheet_path

        _sheet_path(source, "匹配源")
        sheet_headers = {
            key: _read_header_map(source, sheet_number)
            for key, sheet_number in SOURCE_SHEETS.items()
        }
    for index, name in enumerate(EXTRA_HEADERS, start=97):
        current = sheet_headers["subject"].get(name)
        if current is not None and current != index:
            raise MergeError(f"补贴指标已存在于其他列：{name} → {current}")
        sheet_headers["subject"][name] = index

    _verify_all_mappings(audits, sheet_headers)
    counts = {
        "subject": sum(audits[key].row_count for key in SUBJECT_ORDER),
        "audience": audits["audience"].row_count,
        "keyword": audits["keyword"].row_count,
    }
    with ZipFile(template) as source:
        for key, sheet_number in SOURCE_SHEETS.items():
            if not _has_at_least_rows(source, sheet_number, counts[key] + 1):
                raise MergeError(f"{key} 原表公式行不足，不能安全沿用左侧公式")
    return MergePlan(template, output, audits, sheet_headers, counts)


def build_merged_workbook(
    plan: MergePlan,
    progress: Callable[[int, str], None] | None = None,
    *,
    latest_date: date | None = None,
) -> Path:
    """生成新工作簿；指定最新日时，在发布前刷新汇总透视表。"""
    if latest_date is None:
        return _build_merged_workbook_file(plan, progress)
    if latest_date != max(audit.last_date for audit in plan.audits.values()):
        raise MergeError("透视表最新日必须与本次 CSV 数据截止日一致")
    if plan.output.exists():
        raise MergeError(f"输出文件已存在，拒绝覆盖：{plan.output}")

    stage = plan.output.with_name(f".{plan.output.stem}.{uuid4().hex}.stage.xlsx")
    stage_plan = replace(plan, output=stage)
    try:
        def build_progress(percent: int, message: str) -> None:
            if progress is not None:
                progress(min(65, int(percent * 0.65)), message)

        _build_merged_workbook_file(stage_plan, build_progress)
        if progress is not None:
            progress(67, "启动 Excel 原生透视表刷新")
        from .pivot_refresh import refresh_summary_pivots

        refresh_summary_pivots(
            stage,
            latest_date,
            progress=progress,
        )
        if progress is not None:
            progress(98, "校验刷新后的工作簿结构")
        _verify_zip_output(stage, stage_plan)
        stage.replace(plan.output)
        if progress is not None:
            progress(100, "日期筛选和透视汇总已更新，工作簿已生成")
    except Exception:
        # 失败时不发布不完整文件；stage 名称由本次调用独占，可安全清理。
        for candidate in (stage, stage.with_suffix(stage.suffix + ".partial")):
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return plan.output


def _build_merged_workbook_file(
    plan: MergePlan,
    progress: Callable[[int, str], None] | None = None,
) -> Path:
    """流式生成新文件；任何失败均不留下正式输出。"""
    plan.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = plan.output.with_suffix(plan.output.suffix + ".partial")
    if temporary.exists():
        raise MergeError(f"发现上次未完成的临时文件，请先核对：{temporary}")
    total_rows = sum(plan.row_counts.values())
    written_by_sheet = {key: 0 for key in SOURCE_SHEETS}
    last_percent = -1

    def report_rows(sheet_key: str, rows_written: int) -> None:
        nonlocal last_percent
        written_by_sheet[sheet_key] = rows_written
        if progress is None:
            return
        written = sum(written_by_sheet.values())
        percent = min(90, int(written * 90 / max(total_rows, 1)))
        if percent != last_percent:
            progress(percent, f"正在写入源表数据：{written:,}/{total_rows:,} 行")
            last_percent = percent

    try:
        if progress is not None:
            progress(0, "开始整理并写入源表数据")
        with ZipFile(plan.template) as source, ZipFile(temporary, "w", allowZip64=True) as target:
            for item in source.infolist():
                if item.is_dir():
                    target.writestr(item, b"")
                    continue
                if item.filename == "xl/workbook.xml":
                    payload = _require_full_calculation(source.read(item.filename))
                    target.writestr(item, payload)
                    continue
                key = next(
                    (
                        name
                        for name, number in SOURCE_SHEETS.items()
                        if item.filename == f"xl/worksheets/sheet{number}.xml"
                    ),
                    None,
                )
                with source.open(item) as input_file, target.open(item, "w", force_zip64=True) as output_file:
                    if key is None:
                        shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
                    else:
                        _rewrite_source_sheet(input_file, output_file, plan, key, report_rows)
        if progress is not None:
            progress(95, "校验新工作簿结构与文件完整性")
        _verify_zip_output(temporary, plan)
        temporary.replace(plan.output)
        if progress is not None:
            progress(100, "整理完成，新工作簿已生成")
    except Exception:
        # 保留 partial 供调查；不发布看似完整的正式文件。
        raise
    return plan.output


def _audit_csv(
    key: str, path: Path, expected_start: date, expected_end: date
) -> SourceAudit:
    with path.open("r", encoding="gb18030", newline="") as source:
        reader = csv.reader(source)
        headers = tuple(next(reader, ()))
        if not headers or headers[0] != "日期" or len(set(headers)) != len(headers):
            raise MergeError(f"{key} CSV 表头缺失、重复或首列不是日期")
        count = 0
        first = date.max
        last = date.min
        for row in reader:
            if len(row) != len(headers):
                raise MergeError(f"{key} CSV 第 {count + 2} 行列数不一致")
            try:
                day = date.fromisoformat(row[0])
            except ValueError as exc:
                raise MergeError(f"{key} CSV 第 {count + 2} 行日期无效") from exc
            first = min(first, day)
            last = max(last, day)
            count += 1
    if count == 0 or (first, last) != (expected_start, expected_end):
        raise MergeError(
            f"{key} CSV 日期范围或数据行数异常：{first} 至 {last}，{count} 行；"
            f"预期 {expected_start} 至 {expected_end}"
        )
    return SourceAudit(key, path, headers, count, first, last)


def _read_header_map(source: ZipFile, sheet_number: int) -> dict[str, int]:
    name = f"xl/worksheets/sheet{sheet_number}.xml"
    with source.open(name) as member:
        _, remainder = _read_through(member, b"<sheetData>")
        row, _ = _next_row(member, remainder)
    if row is None:
        raise MergeError(f"源表 {sheet_number} 缺少表头行")
    shared = _shared_strings(source)
    parsed = ET.fromstring(row)
    headers: dict[str, int] = {}
    for cell in parsed.findall("c"):
        value = cell.find("v")
        if value is None or value.text is None:
            continue
        if cell.get("t") == "s":
            label = shared[int(value.text)]
        elif cell.get("t") == "inlineStr":
            label = "".join(cell.find("is").itertext())
        else:
            continue
        if label in headers:
            raise MergeError(f"源表 {sheet_number} 表头重复：{label}")
        headers[label] = _column_number(cell.get("r", ""))
    return headers


def _shared_strings(source: ZipFile) -> list[str]:
    root = ET.fromstring(source.read("xl/sharedStrings.xml"))
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    return ["".join(element.itertext()) for element in root.findall(namespace + "si")]


def _verify_all_mappings(
    audits: dict[str, SourceAudit], headers: dict[str, dict[str, int]]
) -> None:
    assignment = {
        "product": "subject", "plan": "subject", "content": "subject",
        "audience": "audience", "keyword": "keyword",
    }
    for report_key, audit in audits.items():
        sheet_key = assignment[report_key]
        destination = headers[sheet_key]
        missing = [name for name in audit.headers if name not in destination]
        if missing:
            raise MergeError(f"{report_key} 有无法对应的列：{missing}")
        if report_key == "plan" and audit.headers[:7] != (
            "日期", "场景ID", "场景名字", "原二级场景ID", "原二级场景名字", "计划ID", "计划名字"
        ):
            raise MergeError("计划报表前七列与预期不符")
        expected_min = START_COLUMNS[sheet_key]
        if destination["日期"] != expected_min:
            raise MergeError(f"{sheet_key} 日期起始列不匹配")


def _has_at_least_rows(source: ZipFile, sheet_number: int, needed: int) -> bool:
    with source.open(f"xl/worksheets/sheet{sheet_number}.xml") as member:
        prefix, _ = _read_through(member, b"<sheetData>")
    match = re.search(rb'<dimension ref="[A-Z]+1:[A-Z]+([0-9]+)"', prefix)
    return match is not None and int(match.group(1)) >= needed


def _rewrite_source_sheet(
    source: BinaryIO,
    target: BinaryIO,
    plan: MergePlan,
    sheet_key: str,
    progress: Callable[[str, int], None] | None = None,
) -> None:
    prefix, buffer = _read_through(source, b"<sheetData>")
    last_row = plan.row_counts[sheet_key] + 1
    max_col = MAX_COLUMNS[sheet_key]
    new_dimension = f"A1:{_column_letters(max_col)}{last_row}".encode("ascii")
    prefix = re.sub(rb'<dimension ref="[^"]+"', b'<dimension ref="' + new_dimension + b'"', prefix, count=1)
    prefix = prefix.replace(b' filterMode="1"', b'')
    target.write(prefix)

    header, buffer = _next_row(source, buffer)
    if header is None:
        raise MergeError(f"{sheet_key} 原表没有表头")
    if sheet_key == "subject":
        header = _add_extra_headers(header)
    target.write(header)

    date_style = None
    for row_number, values in enumerate(_rows_for_sheet(plan, sheet_key), start=2):
        original, buffer = _next_row(source, buffer)
        if original is None:
            raise MergeError(f"{sheet_key} 原表公式行不足：{row_number}")
        if date_style is None:
            date_cell = ET.fromstring(original).find(
                f'c[@r="{_column_letters(START_COLUMNS[sheet_key])}{row_number}"]'
            )
            date_style = date_cell.get("s") if date_cell is not None else None
            if date_style is None:
                raise MergeError(f"{sheet_key} 原表日期列缺少可沿用的单元格格式")
        target.write(
            _replace_row(
                original, row_number, values, START_COLUMNS[sheet_key], max_col,
                date_style=date_style,
            )
        )
        completed = row_number - 1
        if progress is not None and (
            completed % 500 == 0 or completed == plan.row_counts[sheet_key]
        ):
            progress(sheet_key, completed)
    buffer = _skip_to_end_sheet_data(source, buffer)
    suffix = buffer + source.read()
    suffix = _reset_auto_filter(suffix, new_dimension)
    target.write(suffix)


def _rows_for_sheet(plan: MergePlan, sheet_key: str) -> Iterator[dict[int, tuple[str, str]]]:
    keys = SUBJECT_ORDER if sheet_key == "subject" else (sheet_key,)
    headers = plan.headers[sheet_key]
    for report_key in keys:
        audit = plan.audits[report_key]
        with audit.path.open("r", encoding="gb18030", newline="") as source:
            reader = csv.DictReader(source)
            for raw in reader:
                values = {headers[name]: (value, name) for name, value in raw.items()}
                if report_key == "plan":
                    scene = raw["场景名字"]
                    values[19] = (scene, "主体ID")
                    values[20] = (scene, "主体类型")
                elif report_key == "content":
                    values[19] = (raw["主体名称"], "主体ID")
                yield values


def _replace_row(
    original: bytes,
    row_number: int,
    values: dict[int, tuple[str, str]],
    first_raw_column: int,
    max_column: int,
    *,
    date_style: str | None = None,
) -> bytes:
    row = ET.fromstring(original)
    if int(row.get("r", "0")) != row_number:
        raise MergeError(f"原表行不连续：期望 {row_number}，得到 {row.get('r')}")
    row.attrib.pop("hidden", None)
    row.set("spans", f"1:{max_column}")
    existing_style = {}
    for cell in list(row):
        if cell.tag != "c":
            continue
        col = _column_number(cell.get("r", ""))
        if cell.get("s") is not None:
            existing_style[col] = cell.get("s")
        if col >= first_raw_column:
            row.remove(cell)
        else:
            formula = cell.find("f")
            if formula is not None:
                cached = cell.find("v")
                if cached is not None:
                    cell.remove(cached)

    for col in range(first_raw_column, max_column + 1):
        entry = values.get(col)
        style = existing_style.get(col)
        if entry is None:
            # 保留有样式的空格，尤其是计划区 U 列。
            if style is not None:
                attrs = {"r": f"{_column_letters(col)}{row_number}", "s": style}
                ET.SubElement(row, "c", attrs)
            continue
        value, header = entry
        attrs = {"r": f"{_column_letters(col)}{row_number}"}
        if style is None and col == first_raw_column and header == "日期":
            style = date_style
        if style is not None:
            attrs["s"] = style
        cell = ET.SubElement(row, "c", attrs)
        _set_cell_value(cell, value, header)
    return ET.tostring(row, encoding="utf-8", short_empty_elements=True)


def _set_cell_value(cell: ET.Element, value: str, header: str) -> None:
    if value == "":
        return
    if header == "日期":
        try:
            day = date.fromisoformat(value)
        except ValueError as exc:
            raise MergeError(f"无法写入的日期：{value}") from exc
        ET.SubElement(cell, "v").text = str((day - EXCEL_EPOCH).days)
        return
    is_text = (
        header == "主体ID" and not value.isdigit()
        or any(marker in header for marker in ("名字", "名称", "类型"))
        or value.startswith("0") and len(value) > 1 and value[1].isdigit()
        or value.isdigit() and len(value.lstrip("0")) > 15
    )
    if not is_text and _NUMERIC.fullmatch(value):
        ET.SubElement(cell, "v").text = value
        return
    cell.set("t", "inlineStr")
    inline = ET.SubElement(cell, "is")
    text_node = ET.SubElement(inline, "t")
    if value != value.strip():
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = value


def _add_extra_headers(raw: bytes) -> bytes:
    row = ET.fromstring(raw)
    existing = {_column_number(c.get("r", "")): c for c in row.findall("c")}
    for col in range(97, 101):
        cell = existing.get(col)
        if cell is not None and (cell.find("v") is not None or cell.find("f") is not None):
            raise MergeError(f"目标表 {cell.get('r')} 非空，不能添加补贴表头")
        if cell is not None:
            row.remove(cell)
    style = existing.get(96).get("s") if existing.get(96) is not None else None
    for col, label in enumerate(EXTRA_HEADERS, start=97):
        attrs = {"r": f"{_column_letters(col)}1", "t": "inlineStr"}
        if style is not None:
            attrs["s"] = style
        cell = ET.SubElement(row, "c", attrs)
        ET.SubElement(ET.SubElement(cell, "is"), "t").text = label
    row.set("spans", "1:100")
    return ET.tostring(row, encoding="utf-8", short_empty_elements=True)


def _read_through(source: BinaryIO, marker: bytes) -> tuple[bytes, bytes]:
    buffer = bytearray()
    while True:
        chunk = source.read(65536)
        if not chunk:
            raise MergeError(f"工作表 XML 缺少标记：{marker!r}")
        buffer.extend(chunk)
        index = buffer.find(marker)
        if index >= 0:
            end = index + len(marker)
            return bytes(buffer[:end]), bytes(buffer[end:])
        if len(buffer) > 2_000_000:
            raise MergeError("工作表 XML 头部异常过长")


def _next_row(source: BinaryIO, initial: bytes) -> tuple[bytes | None, bytes]:
    buffer = bytearray(initial)
    while True:
        start = buffer.find(b"<row ")
        sheet_end = buffer.find(b"</sheetData>")
        if sheet_end >= 0 and (start < 0 or sheet_end < start):
            return None, bytes(buffer[sheet_end:])
        if start >= 0:
            opening_end = buffer.find(b">", start)
            if opening_end >= 0 and buffer[opening_end - 1:opening_end] == b"/":
                return bytes(buffer[start:opening_end + 1]), bytes(buffer[opening_end + 1:])
            end = buffer.find(b"</row>", start)
            if end >= 0:
                return bytes(buffer[start:end + 6]), bytes(buffer[end + 6:])
        chunk = source.read(1024 * 1024)
        if not chunk:
            raise MergeError("工作表 XML 在数据区提前结束")
        buffer.extend(chunk)
        if len(buffer) > 8_000_000:
            raise MergeError("单行工作表 XML 异常过长")


def _skip_to_end_sheet_data(source: BinaryIO, initial: bytes) -> bytes:
    marker = b"</sheetData>"
    buffer = initial
    while True:
        index = buffer.find(marker)
        if index >= 0:
            return buffer[index:]
        chunk = source.read(1024 * 1024)
        if not chunk:
            raise MergeError("工作表 XML 缺少 sheetData 结束标记")
        buffer = buffer[-len(marker):] + chunk


def _reset_auto_filter(suffix: bytes, dimension: bytes) -> bytes:
    replacement = b'<autoFilter ref="' + dimension + b'"/>'
    suffix = re.sub(rb'<autoFilter\b[^>]*>.*?</autoFilter>', replacement, suffix, flags=re.DOTALL)
    suffix = re.sub(rb'<autoFilter\b[^>]*/>', replacement, suffix)
    return suffix


def _require_full_calculation(payload: bytes) -> bytes:
    match = re.search(rb'<calcPr\b[^>]*/>', payload)
    if match:
        tag = match.group()
        tag = re.sub(rb'\s+(?:fullCalcOnLoad|forceFullCalc)="[^"]*"', b'', tag)
        tag = tag[:-2] + b' fullCalcOnLoad="1" forceFullCalc="1"/>'
        return payload[:match.start()] + tag + payload[match.end():]
    return payload.replace(b"</workbook>", b'<calcPr fullCalcOnLoad="1" forceFullCalc="1"/></workbook>')


def _column_number(reference: str) -> int:
    match = _CELL_REFERENCE.fullmatch(reference)
    if match is None:
        raise MergeError(f"无效的单元格地址：{reference}")
    result = 0
    for char in match.group(1):
        result = result * 26 + ord(char) - ord("A") + 1
    return result


def _column_letters(number: int) -> str:
    letters = ""
    while number:
        number, mod = divmod(number - 1, 26)
        letters = chr(65 + mod) + letters
    return letters


def _verify_zip_output(path: Path, plan: MergePlan) -> None:
    with ZipFile(path) as book:
        bad = book.testzip()
        if bad:
            raise MergeError(f"新工作簿 ZIP 校验失败：{bad}")
        for key, number in SOURCE_SHEETS.items():
            with book.open(f"xl/worksheets/sheet{number}.xml") as member:
                prefix, remainder = _read_through(member, b"<sheetData>")
                expected = plan.row_counts[key] + 1
                match = re.search(rb'<dimension ref="[A-Z]+1:[A-Z]+([0-9]+)"', prefix)
                if match is None or int(match.group(1)) != expected:
                    raise MergeError(f"{key} 输出行范围校验失败")
                header, remainder = _next_row(member, remainder)
                first, _ = _next_row(member, remainder)
                if header is None or first is None:
                    raise MergeError(f"{key} 输出缺少表头或首条数据")

