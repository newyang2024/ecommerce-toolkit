from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class ReportPageSpec:
    key: str
    route: str
    route_query: str
    menu_text: str
    heading_text: str
    required_labels: tuple[str, ...]


REPORT_SPECS: tuple[ReportPageSpec, ...] = (
    ReportPageSpec(
        key="plan",
        route="/report/campaign",
        route_query="rptType=campaign&isRequestedQztDefaultSet=1",
        menu_text="计划报表",
        heading_text="计划报表",
        required_labels=("营销场景", "转化统计方式", "数据汇总周期", "维度"),
    ),
    ReportPageSpec(
        key="product",
        route="/report/item_promotion",
        route_query="rptType=item_promotion&isRequestedQztDefaultSet=1",
        menu_text="商品报表",
        heading_text="商品报表",
        required_labels=("营销场景", "转化统计方式", "数据汇总周期", "维度"),
    ),
    ReportPageSpec(
        key="content",
        route="/report/other_promotion",
        route_query="rptType=other_promotion",
        menu_text="内容报表",
        heading_text="内容报表",
        required_labels=("营销场景", "转化统计方式", "数据汇总周期", "维度"),
    ),
    ReportPageSpec(
        key="keyword",
        route="/report/bidword",
        route_query="rptType=bidword",
        menu_text="关键词报表",
        heading_text="关键词报表",
        required_labels=("转化统计方式", "数据汇总周期", "维度"),
    ),
    ReportPageSpec(
        key="audience",
        route="/report/crowd",
        route_query="rptType=crowd&isRequestedQztDefaultSet=1",
        menu_text="人群报表",
        heading_text="人群报表",
        required_labels=("营销场景", "转化统计方式", "数据汇总周期", "维度"),
    ),
)

DOWNLOAD_BUTTON_TEXT = "下载报表"
MAIN_MENU_SELECTOR = "#universalBP_common_layout_main_menu"
REPORT_TITLE_SELECTOR = ".mxgc-grid-title"
DATE_RANGE_SELECTOR = ".mxgc-calendar-rangepicker"


def menu_locator(page, spec: ReportPageSpec):
    return page.locator(MAIN_MENU_SELECTOR).get_by_text(spec.menu_text, exact=True)


def heading_locator(page, spec: ReportPageSpec):
    return page.locator(REPORT_TITLE_SELECTOR).get_by_text(
        spec.heading_text, exact=True
    )


def date_range_locator(page):
    return page.locator(DATE_RANGE_SELECTOR)


def download_button_candidates(page):
    return (
        page.get_by_role("button", name=DOWNLOAD_BUTTON_TEXT, exact=True),
        page.get_by_text(DOWNLOAD_BUTTON_TEXT, exact=True),
    )


def report_page_url(
    entry_url: str,
    spec: ReportPageSpec,
    start_date: date | None = None,
    end_date: date | None = None,
) -> str:
    """基于配置入口构造站内 hash 路由，不依赖易重复的菜单文字。"""
    if (start_date is None) != (end_date is None):
        raise ValueError("开始日期和结束日期必须同时提供")
    parts = urlsplit(entry_url)
    query = list(parse_qsl(spec.route_query, keep_blank_values=True))
    if start_date is not None and end_date is not None:
        query.extend(
            (
                ("startTime", start_date.isoformat()),
                ("endTime", end_date.isoformat()),
            )
        )
        # 计划报表需要“计划、时间”维度；其他报表不能复用这组维度，
        # 否则商品报表的“商品”维度会被页面禁用。
        if spec.key == "plan":
            query.append(("queryDomains", '["campaign","date"]'))
    fragment = f"!{spec.route}?{urlencode(query)}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", fragment))


def is_expected_report_url(url: str, spec: ReportPageSpec) -> bool:
    return f"#!{spec.route}" in url

