from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from marketing_calendar.config import AppConfig
from marketing_calendar.selectors import (
    REPORT_SPECS,
    date_range_locator,
    download_button_candidates,
    heading_locator,
    is_expected_report_url,
    menu_locator,
    report_page_url,
)


class SurveyError(RuntimeError):
    """页面勘测失败。"""


@dataclass(frozen=True)
class LocatorObservation:
    name: str
    total_count: int
    visible_count: int


@dataclass(frozen=True)
class ReportObservation:
    key: str
    url: str
    menu: LocatorObservation
    heading: LocatorObservation
    download_by_role: LocatorObservation
    download_by_text: LocatorObservation
    labels: tuple[LocatorObservation, ...]
    date_range: LocatorObservation
    date_input_count: int
    route_matched: bool
    locator_structures: dict[str, tuple[str, ...]]
    visible_button_texts: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class SurveyResult:
    path: Path
    succeeded: int
    failed: int


def _observe(name: str, locator) -> LocatorObservation:
    total = locator.count()
    visible = 0
    for index in range(total):
        try:
            if locator.nth(index).is_visible():
                visible += 1
        except Exception:
            continue
    return LocatorObservation(name=name, total_count=total, visible_count=visible)


def _unique_visible(locator, description: str):
    visible = []
    for index in range(locator.count()):
        item = locator.nth(index)
        try:
            if item.is_visible():
                visible.append(item)
        except Exception:
            continue
    if len(visible) != 1:
        raise SurveyError(f"{description} 需要唯一可见元素，实际为 {len(visible)} 个")
    return visible[0]


def _structure(locator, limit: int = 6) -> tuple[str, ...]:
    """记录元素及其祖先的标签/类名，不采集业务文本或输入值。"""
    results: list[str] = []
    for index in range(min(locator.count(), limit)):
        item = locator.nth(index)
        try:
            if not item.is_visible():
                continue
            value = item.evaluate(
                """element => {
                    const parts = [];
                    let node = element;
                    for (let depth = 0; node && depth < 5; depth += 1) {
                        const tag = node.tagName.toLowerCase();
                        const id = node.id ? `#${node.id}` : '';
                        const classes = [...node.classList]
                            .slice(0, 4)
                            .map(name => `.${name}`)
                            .join('');
                        const role = node.getAttribute('role');
                        parts.push(`${tag}${id}${classes}${role ? `[role=${role}]` : ''}`);
                        node = node.parentElement;
                    }
                    return parts.join(' < ');
                }"""
            )
            if value not in results:
                results.append(value)
        except Exception:
            continue
    return tuple(results)


def _date_candidates(page):
    return page.locator(
        "input:visible, "
        "[class*='date' i]:visible, "
        "[class*='picker' i]:visible, "
        "[class*='calendar' i]:visible"
    )


def _collect_report(page, spec) -> ReportObservation:
    menu = _observe("menu", menu_locator(page, spec))
    heading = _observe("heading", heading_locator(page, spec))
    download_role, download_text = download_button_candidates(page)
    labels = tuple(
        _observe(label, page.get_by_text(label, exact=True))
        for label in spec.required_labels
    )
    buttons = page.locator("button:visible").all_inner_texts()
    button_texts = tuple(dict.fromkeys(text.strip() for text in buttons if text.strip()))
    date_inputs = page.locator(
        "input[placeholder*='日期']:visible, "
        "input[placeholder*='开始']:visible, "
        "input[placeholder*='结束']:visible, "
        ".ant-picker-range input:visible"
    ).count()
    date_candidates = _date_candidates(page)
    return ReportObservation(
        key=spec.key,
        url=page.url,
        menu=menu,
        heading=heading,
        download_by_role=_observe("download_by_role", download_role),
        download_by_text=_observe("download_by_text", download_text),
        labels=labels,
        date_range=_observe("date_range", date_range_locator(page)),
        date_input_count=date_inputs,
        route_matched=is_expected_report_url(page.url, spec),
        locator_structures={
            "menu_or_heading": _structure(menu_locator(page, spec)),
            "download_button": _structure(download_role),
            "date_candidates": _structure(date_candidates, limit=12),
        },
        visible_button_texts=button_texts,
    )


def survey_report_pages(page: Any, config: AppConfig) -> SurveyResult:
    """只读勘测五类报表；不会点击下载、提交或修改页面数据。"""
    observations: list[ReportObservation] = []
    for spec in REPORT_SPECS:
        try:
            page.goto(
                report_page_url(config.site.report_url, spec),
                wait_until="domcontentloaded",
                timeout=config.browser.timeout_ms * 2,
            )
            download_button_candidates(page)[0].wait_for(
                state="visible",
                timeout=config.browser.timeout_ms,
            )
            time.sleep(0.5)
            observation = _collect_report(page, spec)
            _unique_visible(menu_locator(page, spec), f"{spec.menu_text}侧栏菜单")
            _unique_visible(heading_locator(page, spec), f"{spec.menu_text}页面标题")
            _unique_visible(date_range_locator(page), f"{spec.menu_text}日期范围控件")
            _unique_visible(
                download_button_candidates(page)[0],
                f"{spec.menu_text}下载按钮",
            )
            if not observation.route_matched:
                raise SurveyError(f"{spec.menu_text}路由不匹配：{page.url}")
            observations.append(observation)
        except Exception as exc:
            observations.append(
                ReportObservation(
                    key=spec.key,
                    url=page.url,
                    menu=_observe("menu", menu_locator(page, spec)),
                    heading=_observe("heading", heading_locator(page, spec)),
                    download_by_role=LocatorObservation("download_by_role", 0, 0),
                    download_by_text=LocatorObservation("download_by_text", 0, 0),
                    labels=(),
                    date_range=_observe("date_range", date_range_locator(page)),
                    date_input_count=0,
                    route_matched=is_expected_report_url(page.url, spec),
                    locator_structures={},
                    visible_button_texts=(),
                    error=str(exc),
                )
            )

    now = datetime.now(ZoneInfo(config.timezone))
    target_dir = config.paths.logs / "diagnostics"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"selector_survey_{now:%Y%m%d_%H%M%S}.json"
    payload = {
        "surveyed_at": now.isoformat(),
        "report_count": len(observations),
        "succeeded": sum(item.error is None for item in observations),
        "failed": sum(item.error is not None for item in observations),
        "reports": [asdict(item) for item in observations],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return SurveyResult(
        path=path,
        succeeded=payload["succeeded"],
        failed=payload["failed"],
    )

