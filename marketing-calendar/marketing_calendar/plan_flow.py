from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs

from marketing_calendar.config import AppConfig
from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.report_rules import PlanReportRequest
from marketing_calendar.report_rules import (
    PLAN_DIMENSION_VALUES,
    PLAN_SCENARIO_GROUP_VALUE,
    PLAN_SCENARIO_VALUES,
)
from marketing_calendar.selectors import (
    REPORT_SPECS,
    date_range_locator,
    download_button_candidates,
    heading_locator,
    is_expected_report_url,
    menu_locator,
    report_page_url,
)


class PlanReportFlowError(RuntimeError):
    """计划报表页面未达到可安全配置筛选条件的状态。"""


@dataclass(frozen=True)
class PlanPageReadiness:
    url: str
    menu_visible: int
    heading_visible: int
    date_range_visible: int
    download_button_visible: int


def build_plan_request(date_range: ReportDateRange) -> PlanReportRequest:
    return PlanReportRequest(date_range=date_range)


def verify_plan_page(
    page: Any, config: AppConfig, date_range: ReportDateRange | None = None
) -> PlanPageReadiness:
    """只导航和校验页面，不修改筛选条件、不点击下载。"""
    spec = next(item for item in REPORT_SPECS if item.key == "plan")
    page.goto(
        report_page_url(
            config.site.report_url,
            spec,
            date_range.start if date_range else None,
            date_range.end if date_range else None,
        ),
        wait_until="domcontentloaded",
        timeout=config.browser.timeout_ms * 2,
    )
    download = download_button_candidates(page)[0]
    download.wait_for(state="visible", timeout=config.browser.timeout_ms)
    date_control = date_range_locator(page)
    date_control.wait_for(state="visible", timeout=config.browser.timeout_ms)
    readiness = PlanPageReadiness(
        url=page.url,
        menu_visible=_visible_count(menu_locator(page, spec)),
        heading_visible=_visible_count(heading_locator(page, spec)),
        date_range_visible=_visible_count(date_control),
        download_button_visible=_visible_count(download),
    )
    if not is_expected_report_url(readiness.url, spec):
        raise PlanReportFlowError(f"计划报表路由不匹配：{readiness.url}")
    for name, count in (
        ("侧栏菜单", readiness.menu_visible),
        ("页面标题", readiness.heading_visible),
        ("日期范围", readiness.date_range_visible),
        ("下载报表按钮", readiness.download_button_visible),
    ):
        if count != 1:
            raise PlanReportFlowError(f"计划报表{name}需要唯一可见元素，实际为 {count} 个")
    if date_range is not None:
        _assert_date_range(page, date_range)
    return readiness


def apply_plan_scenarios(page: Any) -> None:
    """按需求勾选三项计划营销场景并确认，不提交下载任务。"""
    trigger = _marketing_scenario_trigger(page)
    root_group_locator = page.locator(
        f'input[type="checkbox"][value="{PLAN_SCENARIO_GROUP_VALUE}"]'
    )
    if not _has_one_visible(root_group_locator):
        for attempt in range(2):
            trigger = _marketing_scenario_trigger(page)
            if "mx-trigger-open" not in (trigger.get_attribute("class") or ""):
                trigger.click()
            try:
                root_group_locator.wait_for(state="visible", timeout=3_000)
                break
            except Exception as exc:
                if attempt == 1:
                    raise PlanReportFlowError(
                        "营销场景一级菜单未在点击后打开；"
                        "请检查页面控件是否变更，流程未修改筛选或提交下载"
                    ) from exc
    root_group = _option_input(page, PLAN_SCENARIO_GROUP_VALUE, "内容营销")
    root_group.wait_for(state="visible")
    root_menu_item = root_group.locator("xpath=../../..")
    _unique_visible(root_menu_item, "内容营销一级菜单项")

    # 子级菜单的 mouseover 实际绑定在 mx-output-link 上，而非外层行。
    # 勾选后组件可能关闭或重绘菜单；每个子项都重新展开。
    for name in ("超级直播", "短直联动"):
        option = _open_plan_submenu_option(page, PLAN_SCENARIO_VALUES[name], name)
        option.wait_for(state="visible")
        _set_checkbox(option, True)

    lead_option = _option_input(
        page, PLAN_SCENARIO_VALUES["线索推广"], "线索推广"
    )
    lead_option.scroll_into_view_if_needed()
    _set_checkbox(lead_option, True)

    for name, value in PLAN_SCENARIO_VALUES.items():
        option = _option_input(page, value, name)
        if not option.is_checked():
            raise PlanReportFlowError(f"营销场景未成功选中：{name}")

    confirm = _unique_visible(page.get_by_text("确定", exact=True), "营销场景确认按钮")
    confirm.click()


def _open_plan_submenu_option(page: Any, value: str, name: str):
    for attempt in range(2):
        trigger = _marketing_scenario_trigger(page)
        if "mx-trigger-open" not in (trigger.get_attribute("class") or ""):
            trigger.click()
        root_group = _option_input(page, PLAN_SCENARIO_GROUP_VALUE, "内容营销")
        root_menu_item = _unique_visible(
            root_group.locator("xpath=../../.."), "内容营销一级菜单项"
        )
        root_menu_item.locator(".mx-output-link").dispatch_event("mouseover")
        try:
            return _option_input(page, value, name)
        except PlanReportFlowError:
            if attempt == 1:
                raise
    raise PlanReportFlowError(f"营销场景选项未出现：{name}")


def apply_plan_dimensions(page: Any) -> None:
    """选择计划与时间两个维度，即需求截图中的“全部”。"""
    dimension = _unique_visible(page.get_by_text("维度", exact=True), "维度标签")
    trigger = _unique_visible(dimension.locator("xpath=.."), "维度下拉框")
    if _all_dimensions_selected(trigger.inner_text()):
        return
    trigger.click()

    select_all = _unique_visible(
        page.locator('input[type="checkbox"][value$="_all"]'), "维度全选选项"
    )
    if not select_all.is_checked():
        select_all.locator("xpath=..").click()

    for value in PLAN_DIMENSION_VALUES:
        option = _unique_visible(
            page.locator(f'input[type="checkbox"][value="{value}"]'),
            f"维度选项：{value}",
        )
        if not option.is_checked():
            raise PlanReportFlowError(f"维度未成功选中：{value}")
    _unique_visible(page.get_by_text("确定", exact=True), "维度确认按钮").click()


def _assert_date_range(page: Any, expected: ReportDateRange) -> None:
    control = _unique_visible(date_range_locator(page), "日期范围控件")
    view = control.get_attribute("mx-view") or ""
    query = parse_qs(view.partition("?")[2])
    start = (query.get("start") or [None])[0]
    end = (query.get("end") or [None])[0]
    if (start, end) != (expected.start.isoformat(), expected.end.isoformat()):
        raise PlanReportFlowError(
            "日期范围未按参数回显："
            f"当前 {start or '空'} 至 {end or '空'}，"
            f"期望 {expected.start} 至 {expected.end}"
        )


def _all_dimensions_selected(control_text: str) -> bool:
    return "".join(control_text.split()) == "维度计划,时间"


def _marketing_scenario_trigger(page: Any):
    label = _unique_visible(
        page.locator(".fixed-title").get_by_text("营销场景", exact=True),
        "营销场景标签",
    )
    trigger = label.locator("xpath=following-sibling::*[1]").locator(".mx-trigger")
    _unique_visible(trigger, "营销场景下拉框")
    return trigger


def _option_input(page: Any, value: str, expected_text: str):
    option = page.locator(f'input[type="checkbox"][value="{value}"]')
    try:
        option.wait_for(state="visible", timeout=3_000)
    except Exception as exc:
        raise PlanReportFlowError(f"营销场景选项未出现：{expected_text}") from exc
    visible = _unique_visible(option, f"营销场景选项：{expected_text}")
    label_text = visible.locator("xpath=..").inner_text().strip()
    if label_text != expected_text:
        raise PlanReportFlowError(
            f"营销场景值与名称不一致：{value} 对应 {label_text!r}，期望 {expected_text!r}"
        )
    return visible


def _set_checkbox(option: Any, expected: bool) -> None:
    if option.is_checked() != expected:
        option.locator("xpath=..").click()


def _is_visible(locator: Any) -> bool:
    try:
        return locator.is_visible()
    except Exception:
        return False


def _has_one_visible(locator: Any) -> bool:
    return sum(_is_visible(locator.nth(index)) for index in range(locator.count())) == 1


def _unique_visible(locator: Any, description: str):
    visible = []
    for index in range(locator.count()):
        item = locator.nth(index)
        if _is_visible(item):
            visible.append(item)
    if len(visible) != 1:
        raise PlanReportFlowError(f"{description}需要唯一可见元素，实际为 {len(visible)} 个")
    return visible[0]


def _visible_count(locator: Any) -> int:
    visible = 0
    for index in range(locator.count()):
        try:
            if locator.nth(index).is_visible():
                visible += 1
        except Exception:
            continue
    return visible
