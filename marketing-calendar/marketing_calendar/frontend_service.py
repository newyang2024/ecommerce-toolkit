"""本地界面的任务编排与只读摘要；沿用命令行的下载和合并实现。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from marketing_calendar.archive import RunArchive
from marketing_calendar.config import AppConfig, load_config
from marketing_calendar.data_merge import build_merged_workbook, prepare_merge
from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.download_runner import prepare_run, run_download


REPORTS = ("plan", "product", "content", "keyword", "audience")
REPORT_LABELS = {
    "plan": "计划报表",
    "product": "商品报表",
    "content": "内容报表",
    "keyword": "关键词报表",
    "audience": "人群报表",
}


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    message: str
    report_key: str | None = None
    run_dir: Path | None = None
    percent: int | None = None


@dataclass(frozen=True)
class RunSummary:
    run_dir: Path
    start_date: str
    end_date: str
    planned: tuple[str, ...]
    completed: tuple[str, ...]
    row_counts: dict[str, int]
    workbook: Path | None
    workbook_bytes: int | None

    @property
    def is_download_complete(self) -> bool:
        return bool(self.planned) and set(self.planned) <= set(self.completed)


def _manifest(run_dir: Path) -> dict:
    path = run_dir / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"运行清单无法读取：{path}") from exc
    if not isinstance(data, dict) or data.get("run_id") != run_dir.name:
        raise ValueError(f"运行清单与目录不匹配：{path}")
    return data


def expected_workbook(run_dir: Path, end_date: str) -> Path:
    return run_dir / f"万相台日报表_{date.fromisoformat(end_date):%Y%m%d}_整理.xlsx"


def inspect_run(run_dir: Path) -> RunSummary:
    run_dir = Path(run_dir).resolve()
    manifest = _manifest(run_dir)
    try:
        period = manifest["date_range"]
        start, end = period["start_date"], period["end_date"]
        date.fromisoformat(start)
        date.fromisoformat(end)
        planned = tuple(manifest["planned_reports"])
        items = manifest["reports"]
        if not isinstance(items, list) or not set(planned) <= set(REPORTS):
            raise ValueError("报表清单无效")
        completed = tuple(item["report_key"] for item in items if isinstance(item, dict))
        counts: dict[str, int] = {}
        for item in items:
            key = item["report_key"]
            for file_info in item.get("files", []):
                counts[key] = counts.get(key, 0) + int(file_info["data_row_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"运行清单内容无效：{run_dir / 'manifest.json'}") from exc
    result = expected_workbook(run_dir, end)
    workbook = result if result.is_file() else None
    return RunSummary(
        run_dir, start, end, planned, completed, counts,
        workbook, workbook.stat().st_size if workbook else None,
    )


def list_runs(output_root: Path) -> tuple[RunSummary, ...]:
    if not output_root.is_dir():
        return ()
    runs = []
    for path in sorted(output_root.glob("*/manifest.json"), reverse=True):
        try:
            runs.append(inspect_run(path.parent))
        except ValueError:
            continue
    return tuple(runs)


def run_pipeline(
    *,
    base_workbook: Path,
    start_date: date | None = None,
    end_date: date | None = None,
    resume_run: Path | None = None,
    output_root: Path | None = None,
    config: AppConfig | None = None,
    emit: Callable[[ProgressEvent], None] | None = None,
) -> RunSummary:
    """后台运行真实流程；既有结果不覆盖，未完成任务仅从原记录续跑。"""
    from marketing_calendar.browser import BrowserManager
    from marketing_calendar.logging_setup import configure_logging

    config = config or load_config()
    emit = emit or (lambda _event: None)
    base_workbook = Path(base_workbook).resolve()
    if not base_workbook.is_file():
        raise ValueError(f"底本文件不存在：{base_workbook}")
    output_root = Path(output_root or config.paths.output).resolve()
    if resume_run is not None and (start_date is not None or end_date is not None):
        raise ValueError("续跑时不能重新指定日期")
    if resume_run is not None:
        run_dir = Path(resume_run).resolve()
        summary = inspect_run(run_dir)
        if not summary.is_download_complete:
            archive, frozen, reports = prepare_run(
                output_root,
                ReportDateRange(date.fromisoformat(summary.start_date), date.fromisoformat(summary.end_date)),
                REPORTS,
                resume_run=run_dir,
            )
        else:
            archive = RunArchive(run_dir.name, run_dir, run_dir / "raw", run_dir / "extracted", run_dir / "diagnostics")
            frozen = ReportDateRange(date.fromisoformat(summary.start_date), date.fromisoformat(summary.end_date))
            reports = summary.planned
        emit(ProgressEvent("run", "已读取原运行记录，将从未完成处继续", run_dir=run_dir))
    else:
        frozen = ReportDateRange.resolve(start_date, end_date, timezone=config.timezone)
        archive = None
        reports = REPORTS

    if set(reports) != set(REPORTS):
        raise ValueError("前端整理流程只支持五表齐全的运行；请用命令行完成部分报表任务")

    if archive is None or not inspect_run(archive.root).is_download_complete:
        emit(ProgressEvent("browser", "连接项目专用 Edge，检查登录状态"))
        logger = configure_logging(config.paths.logs)
        with BrowserManager(config, logger, connect_existing=True) as browser:
            state = browser.wait_for_manual_login()
            if not state.logged_in:
                raise RuntimeError(f"下载流程暂停：{state.reason}")
            if archive is None:
                archive, frozen, reports = prepare_run(output_root, frozen, REPORTS)
                emit(ProgressEvent("run", "已创建本次运行记录", run_dir=archive.root))
            run_download(
                browser.page,
                config,
                archive,
                frozen,
                reports,
                progress=lambda key, phase, message: emit(ProgressEvent(phase, message, key, archive.root)),
            )

    assert archive is not None
    summary = inspect_run(archive.root)
    for key in summary.completed:
        emit(ProgressEvent("complete", "该报表已在运行记录中完成", key, archive.root))
    if not summary.is_download_complete:
        raise RuntimeError("五类报表尚未全部完成，停止数据整理")
    if summary.workbook is not None:
        emit(ProgressEvent("complete", "结果文件已存在，未覆盖或重新整理", run_dir=archive.root))
        return summary

    output = expected_workbook(archive.root, summary.end_date)
    emit(ProgressEvent("merge_check", "校验五份 CSV、列映射和底本", run_dir=archive.root))
    plan = prepare_merge(
        base_workbook, archive.extracted, output,
        expected_start=frozen.start, expected_end=frozen.end,
    )
    emit(ProgressEvent("merging", "正在生成完整 Excel；原文件不会被改写", run_dir=archive.root))
    build_merged_workbook(
        plan,
        latest_date=frozen.end,
        progress=lambda percent, message: emit(
            ProgressEvent("merging", message, run_dir=archive.root, percent=percent)
        ),
    )
    emit(ProgressEvent("complete", "五表下载与数据整理完成", run_dir=archive.root))
    return inspect_run(archive.root)
