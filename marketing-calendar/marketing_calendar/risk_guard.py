from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from marketing_calendar.date_range import ReportDateRange


class ManualVerificationRequired(RuntimeError):
    """网站要求用户手动完成安全验证；自动化必须暂停。"""


class SubmissionUncertain(RuntimeError):
    """提交状态未能唯一确认；禁止自动重复提交。"""


def assert_no_verification(page: Any) -> None:
    """只检测验证浮层，不尝试关闭、点击或完成验证。"""
    dialog = page.locator(".baxia-dialog")
    for index in range(dialog.count()):
        if dialog.nth(index).is_visible():
            raise ManualVerificationRequired(
                "检测到网站安全验证。请在项目专用 Edge 中手动完成，"
                "随后先核对下载任务，再继续；不会自动操作滑块。"
            )


@dataclass(frozen=True)
class SubmissionRecord:
    report_key: str
    date_range: ReportDateRange
    submitted_at: datetime
    baseline_task_ids: frozenset[str]
    status: str
    task_id: str | None = None


class SubmissionJournal:
    """每次运行的提交记录；pending 状态在进程重启后仍阻止重复提交。"""

    def __init__(self, path: Path):
        self.path = path

    def get(self, report_key: str) -> SubmissionRecord | None:
        raw = self._read().get(report_key)
        if raw is None:
            return None
        try:
            return SubmissionRecord(
                report_key=report_key,
                date_range=ReportDateRange(
                    datetime.fromisoformat(raw["start_date"]).date(),
                    datetime.fromisoformat(raw["end_date"]).date(),
                ),
                submitted_at=datetime.fromisoformat(raw["submitted_at"]),
                baseline_task_ids=frozenset(raw["baseline_task_ids"]),
                status=raw["status"],
                task_id=raw.get("task_id"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SubmissionUncertain(f"提交记录损坏，拒绝继续：{self.path}") from exc

    def begin(
        self,
        report_key: str,
        date_range: ReportDateRange,
        submitted_at: datetime,
        baseline_task_ids: Iterable[str],
    ) -> SubmissionRecord:
        from marketing_calendar.download_tasks import REPORT_FILE_PREFIXES

        if report_key not in REPORT_FILE_PREFIXES:
            raise ValueError(f"不支持的报表类型：{report_key}")
        document = self._read()
        if report_key in document:
            raise SubmissionUncertain(
                f"{report_key} 已有提交记录，必须先核对原任务，不能重复提交"
            )
        baseline = frozenset(baseline_task_ids)
        document[report_key] = {
            "start_date": date_range.start.isoformat(),
            "end_date": date_range.end.isoformat(),
            "submitted_at": submitted_at.isoformat(),
            "baseline_task_ids": sorted(baseline),
            "status": "pending",
            "task_id": None,
        }
        self._write(document)
        record = self.get(report_key)
        if record is None:
            raise SubmissionUncertain(f"{report_key} 提交记录写入后不可读取")
        return record

    def reconcile(self, report_key: str, tasks: Iterable[Any]) -> Any:
        """仅用提交前基线之后的唯一匹配任务确认提交；不负责重试。"""
        from marketing_calendar.download_tasks import (
            DownloadTaskError,
            match_new_task,
            new_tasks_since,
        )

        record = self.get(report_key)
        if record is None:
            raise SubmissionUncertain(f"{report_key} 没有待核对的提交记录")
        if record.status == "confirmed":
            raise SubmissionUncertain(f"{report_key} 已确认任务 {record.task_id}，不能重复核对")
        if record.status != "pending":
            raise SubmissionUncertain(f"{report_key} 状态无法识别：{record.status}")
        candidates = new_tasks_since(record.baseline_task_ids, tasks)
        try:
            matched = match_new_task(
                candidates, report_key, record.date_range, record.submitted_at
            )
        except DownloadTaskError as exc:
            raise SubmissionUncertain(
                f"{report_key} 尚未找到唯一新任务；保留待核对状态，禁止自动重提"
            ) from exc
        document = self._read()
        document[report_key]["status"] = "confirmed"
        document[report_key]["task_id"] = matched.task_id
        self._write(document)
        return matched

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SubmissionUncertain(f"提交记录无法读取：{self.path}") from exc
        if not isinstance(value, dict) or value.get("version") != 1:
            raise SubmissionUncertain(f"提交记录格式无效：{self.path}")
        records = value.get("records")
        if not isinstance(records, dict):
            raise SubmissionUncertain(f"提交记录格式无效：{self.path}")
        return records

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"version": 1, "records": records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def submit_once(
    page: Any,
    journal: SubmissionJournal,
    report_key: str,
    date_range: ReportDateRange,
    submitted_at: datetime,
    baseline_task_ids: Iterable[str],
    action: Callable[[], None],
) -> SubmissionRecord:
    """先持久记录，再执行一次页面提交；任何异常都保留 pending。"""
    assert_no_verification(page)
    record = journal.begin(report_key, date_range, submitted_at, baseline_task_ids)
    try:
        action()
    except Exception as exc:
        raise SubmissionUncertain(
            f"{report_key} 提交动作结果不明；请手动验证后核对任务，禁止自动重提"
        ) from exc
    assert_no_verification(page)
    return record


def resume_after_manual_verification(
    page: Any,
    journal: SubmissionJournal,
    report_key: str,
    tasks: Iterable[Any],
) -> Any:
    """用户完成验证后只核对既有任务，不自动再次提交。"""
    assert_no_verification(page)
    return journal.reconcile(report_key, tasks)
