"""只替换现有 Excel 模板的“匹配源”数据，保留其他工作表。"""

from __future__ import annotations

import copy
import posixpath
import re
import shutil
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

from .data_merge import MergeError, _require_full_calculation


MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
ET.register_namespace("", MAIN[1:-1])


def replace_matching_source(template: Path, donor: Path, backup: Path) -> None:
    """原子替换模板的匹配源；失败时原模板不变，备份可用于恢复。"""
    template, donor, backup = map(Path, (template, donor, backup))
    if not template.is_file() or not donor.is_file():
        raise MergeError("模板或更新来源不存在")
    if len({template.resolve(), donor.resolve(), backup.resolve()}) != 3:
        raise MergeError("模板、更新来源和备份路径必须不同")
    if backup.exists():
        raise MergeError(f"备份已存在，不覆盖：{backup}")
    temporary = template.with_suffix(template.suffix + ".matching.partial")
    if temporary.exists():
        raise MergeError(f"临时文件已存在，请先核对：{temporary}")

    with ZipFile(template) as old, ZipFile(donor) as new:
        old_sheet = _sheet_path(old, "匹配源")
        new_sheet = _sheet_path(new, "匹配源")
        replacement = _converted_sheet(old.read(old_sheet), new.read(new_sheet), old, new)

    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, backup)
    with ZipFile(template) as original, ZipFile(temporary, "w", allowZip64=True) as output:
        for item in original.infolist():
            if item.is_dir():
                output.writestr(item, b"")
            elif item.filename == old_sheet:
                output.writestr(item, replacement)
            elif item.filename == "xl/workbook.xml":
                output.writestr(item, _require_full_calculation(original.read(item.filename)))
            else:
                with original.open(item) as source, output.open(item, "w", force_zip64=True) as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
    with ZipFile(temporary) as result:
        invalid = result.testzip()
        if invalid is not None:
            raise MergeError(f"更新后的模板压缩包校验失败：{invalid}")
    temporary.replace(template)


def _sheet_path(book: ZipFile, name: str) -> str:
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    relation_id = None
    for sheet in workbook.findall(f"{MAIN}sheets/{MAIN}sheet"):
        if sheet.get("name") == name:
            relation_id = sheet.get(f"{REL}id")
            break
    if relation_id is None:
        raise MergeError(f"工作簿缺少 {name} 工作表")
    relations = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    for relation in relations.findall(f"{PKG_REL}Relationship"):
        if relation.get("Id") == relation_id:
            target = relation.get("Target", "")
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
            if path not in book.namelist():
                raise MergeError(f"找不到 {name} 的工作表数据：{path}")
            return path
    raise MergeError(f"找不到 {name} 的工作表关系")


def _converted_sheet(old_xml: bytes, new_xml: bytes, template: ZipFile, donor: ZipFile) -> bytes:
    old_root = ET.fromstring(old_xml)
    new_root = ET.fromstring(new_xml)
    old_data = old_root.find(f"{MAIN}sheetData")
    new_data = new_root.find(f"{MAIN}sheetData")
    if old_data is None or new_data is None:
        raise MergeError("匹配源缺少数据区")
    old_shared = list(ET.fromstring(template.read("xl/sharedStrings.xml")))
    shared = list(ET.fromstring(donor.read("xl/sharedStrings.xml")))
    if _headers(old_data, old_shared) != _headers(new_data, shared):
        raise MergeError("新旧匹配源表头不同，拒绝替换")
    old_styles, column_styles = _template_styles(old_data)
    for row in new_data.findall(f"{MAIN}row"):
        for cell in row.findall(f"{MAIN}c"):
            reference = cell.get("r", "")
            column = reference.rstrip("0123456789")
            cell.set("s", old_styles.get(reference, column_styles.get(column, "0")))
            if cell.get("t") != "s":
                continue
            value = cell.find(f"{MAIN}v")
            if value is None or value.text is None:
                raise MergeError(f"共享文字索引缺失：{cell.get('r')}")
            index = int(value.text)
            if not 0 <= index < len(shared):
                raise MergeError(f"共享文字索引越界：{cell.get('r')}")
            cell.remove(value)
            cell.set("t", "inlineStr")
            inline = ET.SubElement(cell, f"{MAIN}is")
            for child in shared[index]:
                inline.append(copy.deepcopy(child))

    dimension = new_root.find(f"{MAIN}dimension")
    if dimension is None or not dimension.get("ref"):
        raise MergeError("更新来源缺少匹配源数据范围")
    new_data_xml = ET.tostring(new_data, encoding="utf-8", short_empty_elements=True)
    match = re.search(rb"<sheetData(?:\s[^>]*)?>.*?</sheetData>", old_xml, re.S)
    if match is None:
        raise MergeError("模板匹配源数据区无法定位")
    result = old_xml[:match.start()] + new_data_xml + old_xml[match.end():]
    result, count = re.subn(
        rb'(<dimension ref=")[^"]+("/>)',
        lambda m: m.group(1) + dimension.get("ref").encode("ascii") + m.group(2),
        result,
        count=1,
    )
    if count != 1:
        raise MergeError("模板匹配源数据范围无法更新")
    ET.fromstring(result)
    return result


def _headers(data: ET.Element, shared: list[ET.Element]) -> tuple[tuple[str, str], ...]:
    first = data.find(f"{MAIN}row")
    if first is None:
        raise MergeError("匹配源表头为空")
    result = []
    for cell in first.findall(f"{MAIN}c"):
        value = cell.find(f"{MAIN}v")
        if cell.get("t") == "s":
            if value is None or value.text is None:
                raise MergeError("匹配源表头共享文字缺失")
            label = "".join(shared[int(value.text)].itertext())
        elif cell.get("t") == "inlineStr":
            inline = cell.find(f"{MAIN}is")
            label = "".join(inline.itertext()) if inline is not None else ""
        elif cell.find(f"{MAIN}f") is not None:
            label = "=" + str(cell.find(f"{MAIN}f").text)
        elif value is not None:
            label = value.text or ""
        else:
            label = ""
        result.append((cell.get("r", ""), label))
    return tuple(result)


def _template_styles(data: ET.Element) -> tuple[dict[str, str], dict[str, str]]:
    by_reference = {}
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    for row in data.findall(f"{MAIN}row"):
        for cell in row.findall(f"{MAIN}c"):
            reference = cell.get("r", "")
            style = cell.get("s", "0")
            by_reference[reference] = style
            if row.get("r") != "1":
                votes[reference.rstrip("0123456789")][style] += 1
    by_column = {column: choices.most_common(1)[0][0] for column, choices in votes.items()}
    return by_reference, by_column
