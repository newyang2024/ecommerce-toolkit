from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable

from marketing_calendar.archive import RunArchive, safe_download_path, validate_downloaded_file
from marketing_calendar.config import AppConfig
from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.risk_guard import assert_no_verification


DOWNLOAD_TASKS_ROUTE = "/report/download-list"
DOWNLOAD_TASKS_URL_SUFFIX = f"#!{DOWNLOAD_TASKS_ROUTE}"

REPORT_FILE_PREFIXES = {
    "plan": "计划报表",
    "product": "商品报表",
    "content": "内容报表",
    "keyword": "关键词报表",
    "audience": "人群报表",
}


class DownloadTaskError(RuntimeError):
    """下载任务列表未达到可安全识别或匹配的状态。"""


@dataclass(frozen=True)
class DownloadTask:
    task_id: str
    status: str
    file_name: str
    attribution_period: str
    date_range: str
    created_date: str

    @property
    def is_ready(self) -> bool:
        return self.status == "生成成功"

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "file_name": self.file_name,
            "attribution_period": self.attribution_period,
            "date_range": self.date_range,
            "created_date": self.created_date,
            "is_ready": self.is_ready,
        }


def open_download_tasks(page: Any, config: AppConfig) -> None:
    """进入下载任务管理页；不创建、下载或删除任何任务。"""
    entry = config.site.report_url.partition("#")[0]
    page.goto(
        f"{entry}{DOWNLOAD_TASKS_URL_SUFFIX}",
        wait_until="domcontentloaded",
        timeout=config.browser.timeout_ms * 2,
    )
    title = page.locator(".mxgc-grid-title").get_by_text("下载任务管理", exact=True)
    title.first.wait_for(state="visible", timeout=config.browser.timeout_ms)
    assert_no_verification(page)
    _unique_visible(title, "下载任务管理标题").wait_for(
        state="visible", timeout=config.browser.timeout_ms
    )
    # 标题先于异步列表渲染；若未确认至少一行真实记录，不能把空列表当作基线。
    page.locator('tr input[type="checkbox"][value]').first.wait_for(
        state="visible", timeout=config.browser.timeout_ms
    )
    assert_no_verification(page)


def snapshot_download_tasks(page: Any) -> tuple[DownloadTask, ...]:
    """读取当前页全部可见任务记录，不操作行内按钮。"""
    assert_no_verification(page)
    rows = page.locator("tr")
    tasks: list[DownloadTask] = []
    seen_ids: set[str] = set()
    for index in range(rows.count()):
        row = rows.nth(index)
        checkbox = row.locator('input[type="checkbox"][value]')
        if checkbox.count() != 1:
            continue
        cells = row.locator("td")
        if cells.count() != 6:
            continue
        task_id = (checkbox.get_attribute("value") or "").strip()
        values = [_normalize_text(cells.nth(cell).inner_text()) for cell in range(1, 6)]
        if not task_id or not all(values) or task_id in seen_ids:
            continue
        seen_ids.add(task_id)
        tasks.append(
            DownloadTask(
                task_id=task_id,
                status=values[0],
                file_name=values[1],
                attribution_period=values[2],
                date_range=values[3],
                created_date=values[4],
            )
        )
    assert_no_verification(page)
    return tuple(tasks)


def task_baseline(tasks: Iterable[DownloadTask]) -> frozenset[str]:
    return frozenset(task.task_id for task in tasks)


def new_tasks_since(
    baseline: Iterable[str], tasks: Iterable[DownloadTask]
) -> tuple[DownloadTask, ...]:
    known = frozenset(baseline)
    return tuple(task for task in tasks if task.task_id not in known)


def match_new_task(
    tasks: Iterable[DownloadTask],
    report_key: str,
    date_range: ReportDateRange,
    submitted_at: datetime,
) -> DownloadTask:
    """只在新增任务中按报表前缀、日期及创建日唯一匹配。"""
    try:
        prefix = REPORT_FILE_PREFIXES[report_key]
    except KeyError as exc:
        raise DownloadTaskError(f"不支持的报表类型：{report_key}") from exc

    expected_range = f"{date_range.start.isoformat()}至{date_range.end.isoformat()}"
    expected_created = submitted_at.date().isoformat()
    matches = [
        task
        for task in tasks
        if task.file_name.startswith(f"{prefix}_")
        and task.date_range == expected_range
        and task.created_date == expected_created
    ]
    if len(matches) != 1:
        raise DownloadTaskError(
            f"新增下载任务无法唯一匹配：报表={report_key}，"
            f"日期={expected_range}，创建日={expected_created}，匹配数={len(matches)}"
        )
    return matches[0]


def wait_for_task(
    fetch: Callable[[], Iterable[DownloadTask]],
    task_id: str,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> DownloadTask:
    """轮询指定 ID；成功返回，超时或记录消失时明确失败。"""
    deadline = time.monotonic() + timeout_seconds
    last_status = "未找到"
    while time.monotonic() <= deadline:
        current = {task.task_id: task for task in fetch()}
        task = current.get(task_id)
        if task is None:
            raise DownloadTaskError(f"下载任务已从列表消失：{task_id}")
        last_status = task.status
        if task.is_ready:
            return task
        time.sleep(poll_interval_seconds)
    raise DownloadTaskError(f"等待下载任务超时：{task_id}，最后状态：{last_status}")


def download_task_file(page: Any, task_id: str, archive: RunArchive) -> str:
    """下载指定任务的原文件至本次 raw 目录，不处理任何其他任务。"""
    assert_no_verification(page)
    row = page.locator("tr").filter(
        has=page.locator(f'input[type="checkbox"][value="{task_id}"]')
    )
    task_row = _unique_visible(row, f"下载任务行：{task_id}")
    # 行内操作区默认隐藏，先悬停在目标数据行使其展开；不能只依赖 DOM 中
    # 已存在的相邻操作行，否则 Playwright 会一直等待不可点击的“下载”按钮。
    task_row.hover()
    action_row = task_row.locator("xpath=following-sibling::tr[1]")
    action_row.scroll_into_view_if_needed()
    download_button = _unique_visible(
        action_row.get_by_role("button", name="下载", exact=True),
        f"下载任务按钮：{task_id}",
    )
    with page.expect_download() as download_info:
        download_button.click()
    download = download_info.value
    target = safe_download_path(archive.raw, download.suggested_filename)
    download.save_as(str(target))
    validate_downloaded_file(target)
    return target.name


def _normalize_text(value: str) -> str:
    without_icon_glyphs = "".join(
        char for char in value if unicodedata.category(char) != "Co"
    )
    return " ".join(without_icon_glyphs.split()).replace(" ", "")


def _unique_visible(locator: Any, description: str):
    visible = []
    for index in range(locator.count()):
        candidate = locator.nth(index)
        try:
            if candidate.is_visible():
                visible.append(candidate)
        except Exception:
            continue
    if len(visible) != 1:
        raise DownloadTaskError(f"{description}需要唯一可见元素，实际为 {len(visible)} 个")
    return visible[0]
