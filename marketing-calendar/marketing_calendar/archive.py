from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from shutil import copyfileobj
from zipfile import BadZipFile, ZipFile

from marketing_calendar.date_range import ReportDateRange


class ArchiveError(RuntimeError):
    """下载文件或本地归档目录不符合安全要求。"""


@dataclass(frozen=True)
class RunArchive:
    run_id: str
    root: Path
    raw: Path
    extracted: Path
    diagnostics: Path


@dataclass(frozen=True)
class TabularFileValidation:
    path: Path
    encoding: str
    column_count: int
    data_row_count: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "path": self.path.name,
            "encoding": self.encoding,
            "column_count": self.column_count,
            "data_row_count": self.data_row_count,
        }


def create_run_archive(
    output_root: Path, date_range: ReportDateRange, now: datetime | None = None
) -> RunArchive:
    timestamp = now or datetime.now()
    run_id = (
        f"{timestamp:%Y%m%dT%H%M%S}_"
        f"{date_range.start:%Y%m%d}_{date_range.end:%Y%m%d}"
    )
    root = output_root / run_id
    if root.exists():
        raise ArchiveError(f"本次运行目录已存在，拒绝覆盖：{root}")
    raw = root / "raw"
    extracted = root / "extracted"
    diagnostics = root / "diagnostics"
    for directory in (raw, extracted, diagnostics):
        directory.mkdir(parents=True, exist_ok=False)
    return RunArchive(run_id, root, raw, extracted, diagnostics)


def safe_download_path(raw_directory: Path, suggested_filename: str) -> Path:
    name = Path(suggested_filename).name
    if name in {"", ".", ".."} or name != suggested_filename:
        raise ArchiveError(f"下载文件名不安全：{suggested_filename!r}")
    target = raw_directory / name
    if target.exists():
        raise ArchiveError(f"下载文件已存在，拒绝覆盖：{target}")
    return target


def validate_downloaded_file(path: Path) -> None:
    if not path.is_file():
        raise ArchiveError(f"下载文件不存在：{path}")
    if path.stat().st_size <= 0:
        raise ArchiveError(f"下载文件为空：{path}")


def safe_extract_zip(
    archive_path: Path, extracted_directory: Path, max_uncompressed_bytes: int
) -> tuple[Path, ...]:
    """仅在运行目录内解压 ZIP，并限制解压总大小。"""
    if max_uncompressed_bytes <= 0:
        raise ArchiveError("最大解压大小必须为正整数")
    root = extracted_directory.resolve()
    try:
        with ZipFile(archive_path) as source:
            members = source.infolist()
            total_size = sum(member.file_size for member in members)
            if total_size > max_uncompressed_bytes:
                raise ArchiveError(
                    f"压缩包解压后大小超限：{total_size} > {max_uncompressed_bytes}"
                )
            files: list[Path] = []
            for member in members:
                target = _safe_member_target(root, member.filename)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as input_file, target.open("xb") as output_file:
                    copyfileobj(input_file, output_file)
                files.append(target)
    except BadZipFile as exc:
        raise ArchiveError(f"无法识别为有效 ZIP 文件：{archive_path}") from exc
    if not files:
        raise ArchiveError(f"压缩包内没有可用文件：{archive_path}")
    return tuple(files)


def _safe_member_target(root: Path, member_name: str) -> Path:
    name = Path(member_name)
    if name.is_absolute() or name.drive:
        raise ArchiveError(f"压缩包包含绝对路径：{member_name!r}")
    target = (root / name).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ArchiveError(f"压缩包包含越界路径：{member_name!r}") from exc
    return target


def validate_csv_file(path: Path) -> TabularFileValidation:
    """验证 CSV 可解码、包含表头和至少一行数据，不改变原文件。"""
    if path.suffix.lower() != ".csv":
        raise ArchiveError(f"当前仅支持 CSV 基础校验：{path}")
    validate_downloaded_file(path)
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            with path.open("r", encoding=encoding, newline="") as source:
                rows = csv.reader(source)
                header = next(rows, None)
                if not header or not any(cell.strip() for cell in header):
                    raise ArchiveError(f"CSV 缺少有效表头：{path}")
                data_rows = sum(1 for row in rows if any(cell.strip() for cell in row))
                if data_rows == 0:
                    raise ArchiveError(f"CSV 不包含数据行：{path}")
                return TabularFileValidation(
                    path=path,
                    encoding=encoding,
                    column_count=len(header),
                    data_row_count=data_rows,
                )
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ArchiveError(f"CSV 编码无法识别：{path}") from last_error


def write_manifest(archive: RunArchive, payload: dict[str, object]) -> Path:
    """写入一次运行的结果清单；同一运行只允许生成一次，避免覆盖。"""
    path = archive.root / "manifest.json"
    if path.exists():
        raise ArchiveError(f"运行清单已存在，拒绝覆盖：{path}")
    document = {"run_id": archive.run_id, **payload}
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_manifest_report(archive: RunArchive, report: dict[str, object]) -> Path:
    """向既有运行清单追加一类报表；同一 report_key 不可重复。"""
    report_key = report.get("report_key")
    if not isinstance(report_key, str) or not report_key:
        raise ArchiveError("清单报表必须包含非空 report_key")
    path = archive.root / "manifest.json"
    if not path.is_file():
        raise ArchiveError(f"运行清单不存在，无法追加：{path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveError(f"运行清单无法读取：{path}") from exc
    reports = document.get("reports")
    if not isinstance(reports, list):
        raise ArchiveError("运行清单 reports 必须为列表")
    if any(item.get("report_key") == report_key for item in reports if isinstance(item, dict)):
        raise ArchiveError(f"运行清单已包含报表：{report_key}")
    reports.append(report)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path
