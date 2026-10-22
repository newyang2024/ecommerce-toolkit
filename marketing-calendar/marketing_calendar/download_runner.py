from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Sequence
from zoneinfo import ZoneInfo

from marketing_calendar.archive import (
    ArchiveError,
    RunArchive,
    append_manifest_report,
    create_run_archive,
    safe_extract_zip,
    validate_csv_file,
    write_manifest,
)
from marketing_calendar.config import AppConfig
from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.download_tasks import (
    DownloadTask,
    DownloadTaskError,
    download_task_file,
    open_download_tasks,
    snapshot_download_tasks,
    task_baseline,
    wait_for_task,
)
from marketing_calendar.report_filters import configure_report, submit_report_dialog
from marketing_calendar.risk_guard import (
    SubmissionJournal,
    SubmissionUncertain,
    assert_no_verification,
    resume_after_manual_verification,
    submit_once,
)


class DownloadRunError(RuntimeError):
    """本次下载运行无法安全继续。"""


def prepare_run(
    output_root: Path,
    date_range: ReportDateRange,
    reports: Sequence[str],
    *,
    resume_run: Path | None = None,
) -> tuple[RunArchive, ReportDateRange, tuple[str, ...]]:
    """新建或读取运行目录；断点续跑不改变原定日期和报表集合。"""
    if resume_run is None:
        _reject_overlapping_unfinished_run(output_root, date_range, reports)
        archive = create_run_archive(output_root, date_range)
        selected = tuple(dict.fromkeys(reports))
        write_manifest(
            archive,
            {
                "date_range": date_range.as_dict(),
                "planned_reports": list(selected),
                "reports": [],
            },
        )
        return archive, date_range, selected

    root = resume_run.resolve()
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        period = manifest["date_range"]
        frozen = ReportDateRange(
            date.fromisoformat(period["start_date"]),
            date.fromisoformat(period["end_date"]),
        )
        selected = tuple(manifest["planned_reports"])
        completed = manifest["reports"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DownloadRunError(f"续跑清单无效：{manifest_path}") from exc
    if (
        manifest.get("run_id") != root.name
        or not selected
        or len(set(selected)) != len(selected)
        or not isinstance(completed, list)
        or not all((root / name).is_dir() for name in ("raw", "extracted", "diagnostics"))
    ):
        raise DownloadRunError(f"续跑目录结构无效：{root}")
    archive = RunArchive(root.name, root, root / "raw", root / "extracted", root / "diagnostics")
    return archive, frozen, selected


def _reject_overlapping_unfinished_run(
    output_root: Path, date_range: ReportDateRange, reports: Sequence[str]
) -> None:
    """有同日期、同报表的未完成运行时，要求续跑而非新建。"""
    if not output_root.is_dir():
        return
    for manifest_path in output_root.glob("*/manifest.json"):
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            if "planned_reports" not in document:
                # 旧版归档未记录计划清单，无法判断缺项；不推断其运行状态。
                continue
            period = document["date_range"]
            planned = set(document["planned_reports"])
            completed = {
                item["report_key"] for item in document["reports"] if isinstance(item, dict)
            }
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DownloadRunError(f"既有运行清单无法核对，请先检查：{manifest_path}") from exc
        if (
            period == date_range.as_dict()
            and set(reports) & (planned - completed)
        ):
            raise DownloadRunError(
                f"存在同日期的未完成报表运行，请使用 --resume-run {manifest_path.parent}"
            )


def run_download(
    page: Any,
    config: AppConfig,
    archive: RunArchive,
    date_range: ReportDateRange,
    reports: Sequence[str],
    progress: Callable[[str, str, str], None] | None = None,
) -> Path:
    """顺序配置、提交、确认及归档；任何不确定状态都停止，不自动重提。"""
    manifest_path = archive.root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    completed = {
        item["report_key"] for item in manifest["reports"] if isinstance(item, dict)
    }
    journal = SubmissionJournal(archive.root / "submission_state.json")
    page.set_viewport_size({"width": 1440, "height": 900})

    def report_progress(report_key: str, phase: str, message: str) -> None:
        if progress is not None:
            progress(report_key, phase, message)

    for report_key in reports:
        if report_key in completed:
            report_progress(report_key, "complete", "已归档，续跑时跳过")
            continue
        report_progress(report_key, "checking", "检查页面和本次任务记录")
        assert_no_verification(page)
        record = journal.get(report_key)
        if record is None:
            open_download_tasks(page, config)
            baseline = task_baseline(snapshot_download_tasks(page))
            report_progress(report_key, "filtering", "设置并核对筛选条件")
            configure_report(page, config, report_key, date_range)
            submitted_at = datetime.now(ZoneInfo(config.timezone))
            report_progress(report_key, "submitting", "提交报表生成任务")
            submit_once(
                page,
                journal,
                report_key,
                date_range,
                submitted_at,
                baseline,
                lambda: submit_report_dialog(page),
            )
            record = journal.get(report_key)
        if record is None or record.date_range != date_range:
            raise SubmissionUncertain(f"{report_key} 的提交记录与本次日期不一致")

        open_download_tasks(page, config)
        report_progress(report_key, "confirming", "核对本次新增任务")
        if record.status == "pending":
            task = _reconcile_new_task(page, config, journal, report_key)
        elif record.status == "confirmed" and record.task_id:
            task = _find_task(snapshot_download_tasks(page), record.task_id)
        else:
            raise SubmissionUncertain(f"{report_key} 的提交状态无法确认")

        if not task.is_ready:
            report_progress(report_key, "waiting", "等待网站生成报表")
            task = wait_for_task(
                lambda: _refresh_and_snapshot(page, config),
                task.task_id,
                config.download.timeout_seconds,
                max(15, config.download.poll_interval_seconds),
            )
        report_progress(report_key, "downloading", "下载并校验归档文件")
        raw_name = download_task_file(page, task.task_id, archive)
        raw_path = archive.raw / raw_name
        if raw_path.suffix.lower() != ".zip":
            raise ArchiveError(f"下载文件不是 ZIP，保留原文件供检查：{raw_path}")
        extracted = safe_extract_zip(
            raw_path, archive.extracted, config.download.max_uncompressed_bytes
        )
        validations = [validate_csv_file(path) for path in extracted]
        append_manifest_report(
            archive,
            {
                "report_key": report_key,
                "task_id": task.task_id,
                "raw_file": raw_name,
                "files": [item.as_dict() for item in validations],
            },
        )
        report_progress(report_key, "complete", "下载、解压和校验完成")
    return manifest_path


def _reconcile_new_task(
    page: Any, config: AppConfig, journal: SubmissionJournal, report_key: str
) -> DownloadTask:
    deadline = time.monotonic() + min(60, config.download.timeout_seconds)
    while True:
        tasks = snapshot_download_tasks(page)
        try:
            return resume_after_manual_verification(page, journal, report_key, tasks)
        except SubmissionUncertain:
            if time.monotonic() >= deadline:
                raise
            time.sleep(max(5, config.download.poll_interval_seconds))
            _refresh_and_snapshot(page, config)


def _refresh_and_snapshot(page: Any, config: AppConfig) -> tuple[DownloadTask, ...]:
    assert_no_verification(page)
    open_download_tasks(page, config)
    return snapshot_download_tasks(page)


def _find_task(tasks: Sequence[DownloadTask], task_id: str) -> DownloadTask:
    matches = [task for task in tasks if task.task_id == task_id]
    if len(matches) != 1:
        raise DownloadTaskError(
            f"已确认任务 {task_id} 不在当前任务列表；请手动核对，不会再次提交"
        )
    return matches[0]
