from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

from marketing_calendar.config import AppConfig
from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.plan_flow import apply_plan_dimensions, apply_plan_scenarios
from marketing_calendar.report_rules import PLAN_SCENARIO_VALUES
from marketing_calendar.risk_guard import assert_no_verification
from marketing_calendar.selectors import REPORT_SPECS, report_page_url


class ReportFilterError(RuntimeError):
    """页面筛选未达到可提交状态。"""


DIMENSIONS = {
    "plan": frozenset(("campaign", "date")),
    "product": frozenset(("promotion", "campaign", "date")),
    "content": frozenset(("promotion", "date", "campaign")),
    "audience": frozenset(("crowd", "promotion", "date", "campaign", "adgroup")),
    "keyword": frozenset(("word", "date", "campaign", "adgroup")),
}
SCENARIOS = {
    "plan": frozenset(PLAN_SCENARIO_VALUES.values()),
    "product": frozenset(("onebpSite", "onebpSearch", "onebpDisplay", "onebpStarShop")),
    "content": frozenset(("onebpShortVideo",)),
    "audience": frozenset(("onebpSearch", "onebpDisplay")),
}


def configure_report(
    page: Any, config: AppConfig, report_key: str, date_range: ReportDateRange
) -> None:
    """按页面实际选项配置报表；不点击下载按钮。"""
    spec = next((item for item in REPORT_SPECS if item.key == report_key), None)
    if spec is None:
        raise ReportFilterError(f"不支持的报表：{report_key}")
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(
        report_page_url(config.site.report_url, spec, date_range.start, date_range.end),
        wait_until="domcontentloaded",
        timeout=config.browser.timeout_ms * 2,
    )
    page.locator(".mxgc-grid-title").get_by_text(
        spec.heading_text, exact=True
    ).first.wait_for(state="visible", timeout=config.browser.timeout_ms)
    page.get_by_role("button", name="下载报表", exact=True).wait_for(
        state="visible", timeout=config.browser.timeout_ms
    )
    assert_no_verification(page)

    if report_key == "plan":
        apply_plan_scenarios(page)
        apply_plan_dimensions(page)
    else:
        if report_key == "product" or report_key == "content":
            _select_all_scenarios(page)
        elif report_key == "audience":
            _select_audience_scenarios(page)
        elif report_key == "keyword":
            attribution = page.locator(".mx-trigger").filter(
                has_text="末次点击归因"
            )
            if attribution.count() != 1 or not attribution.first.is_visible():
                raise ReportFilterError("关键词报表未显示末次点击归因")
        _select_all_dimensions(page, DIMENSIONS[report_key])

    assert_no_verification(page)
    verify_report_filters(page.url, report_key, date_range)


def verify_report_filters(
    url: str, report_key: str, date_range: ReportDateRange
) -> None:
    """提交前验证网站回写到 URL 的日期、场景和维度。"""
    if report_key not in DIMENSIONS:
        raise ReportFilterError(f"不支持的报表：{report_key}")
    fragment = urlsplit(url).fragment
    params = parse_qs(fragment.partition("?")[2])
    if params.get("startTime") != [date_range.start.isoformat()] or params.get(
        "endTime"
    ) != [date_range.end.isoformat()]:
        raise ReportFilterError("报表日期未按本次范围回显")
    try:
        dimensions = frozenset(json.loads(params.get("queryDomains", ["[]"])[0]))
        scenarios = frozenset(json.loads(params.get("bizCodeIn", ["[]"])[0]))
    except (ValueError, TypeError) as exc:
        raise ReportFilterError("报表筛选参数无法解析") from exc
    if dimensions != DIMENSIONS[report_key]:
        raise ReportFilterError(
            f"{report_key} 维度不匹配：{sorted(dimensions)}"
        )
    if report_key in SCENARIOS:
        if scenarios != SCENARIOS[report_key]:
            raise ReportFilterError(
                f"{report_key} 营销场景不匹配：{sorted(scenarios)}"
            )


def submit_report_dialog(page: Any) -> None:
    """执行一次完整提交：打开下载设置弹窗并点击弹窗内“确定”。"""
    assert_no_verification(page)
    page.get_by_role("button", name="下载报表", exact=True).click()
    page.get_by_text("文件名称", exact=True).wait_for(state="visible")
    confirms = page.get_by_role("button", name="确定", exact=True)
    visible = [confirms.nth(i) for i in range(confirms.count()) if confirms.nth(i).is_visible()]
    if len(visible) != 1:
        raise ReportFilterError(f"下载设置确认按钮不唯一：{len(visible)}")
    visible[0].click()
    page.get_by_text("文件名称", exact=True).wait_for(state="hidden")
    assert_no_verification(page)


def _select_all_scenarios(page: Any) -> None:
    trigger = page.locator(".mx-trigger").nth(1)
    trigger.click()
    popup = page.locator(".mx-output-open")
    _click_select_all(popup)
    popup.get_by_role("button", name="确定").click()


def _select_audience_scenarios(page: Any) -> None:
    page.locator(".mx-trigger").nth(1).click()
    popup = page.locator(".mx-output-open")
    for value in ("onebpSearch", "onebpDisplay"):
        checkbox = popup.locator(f'input[type="checkbox"][value="{value}"]')
        if not checkbox.is_checked():
            checkbox.locator("xpath=ancestor::label[1]").click()
    popup.get_by_role("button", name="确定").click()


def _select_all_dimensions(page: Any, expected: frozenset[str]) -> None:
    trigger = page.locator(".mx-trigger").filter(has_text="维度").first
    trigger.scroll_into_view_if_needed()
    trigger.click()
    popup = page.locator(".mx-output-open")
    _click_select_all(popup)
    selected = frozenset(
        popup.locator('input[type="checkbox"]:checked').evaluate_all(
            '(items) => items.map(item => item.value).filter(value => !value.endsWith("_all"))'
        )
    )
    if selected != expected:
        raise ReportFilterError(f"维度全选结果不匹配：{sorted(selected)}")
    popup.get_by_role("button", name="确定").click()


def _click_select_all(popup: Any) -> None:
    select_all = popup.locator('input[type="checkbox"][value$="_all"]')
    try:
        select_all.wait_for(state="visible", timeout=3_000)
    except Exception as exc:
        raise ReportFilterError("全选控件未出现") from exc
    if select_all.count() != 1:
        raise ReportFilterError("全选控件不唯一")
    if not select_all.is_checked():
        popup.get_by_text("全选", exact=True).click()
