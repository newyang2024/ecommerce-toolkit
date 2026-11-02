from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from importlib import metadata
from pathlib import Path
from typing import Sequence

from marketing_calendar import __version__
from marketing_calendar.browser import BrowserError
from marketing_calendar.archive import ArchiveError
from marketing_calendar.config import ConfigError, load_config
from marketing_calendar.date_range import DateRangeError, ReportDateRange
from marketing_calendar.data_merge import MergeError
from marketing_calendar.download_tasks import DownloadTaskError
from marketing_calendar.download_runner import DownloadRunError
from marketing_calendar.edge_session import EdgeSessionError, launch_manual_login_edge
from marketing_calendar.risk_guard import ManualVerificationRequired, SubmissionUncertain
from marketing_calendar.report_filters import ReportFilterError
from marketing_calendar.plan_flow import PlanReportFlowError
from marketing_calendar.survey import SurveyError


EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_PARTIAL = 3

REPORT_CHOICES = ("plan", "product", "content", "keyword", "audience")


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"日期必须使用 YYYY-MM-DD 格式：{value}"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marketing-calendar",
        description="万相台营销场景报表下载与归档工具",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="检查运行环境和配置")
    check.add_argument("--config", type=Path, help="JSON 配置文件路径")
    check.add_argument(
        "--browser-smoke",
        action="store_true",
        help="启动后立即关闭项目专用 Edge，验证直连和浏览器配置",
    )

    inspect = subparsers.add_parser("inspect", help="只读勘测五类报表页面定位器")
    inspect.add_argument("--config", type=Path, help="JSON 配置文件路径")
    inspect.add_argument(
        "--login-timeout",
        type=int,
        help="等待用户手动登录的秒数",
    )

    login = subparsers.add_parser("login", help="启动未连接自动化的项目专用 Edge")
    login.add_argument("--config", type=Path, help="JSON 配置文件路径")

    plan_preview = subparsers.add_parser(
        "plan-preview", help="预览计划报表筛选规则，不提交下载任务"
    )
    plan_preview.add_argument("--config", type=Path, help="JSON 配置文件路径")
    plan_preview.add_argument("--start-date", type=_iso_date, help="开始日期 YYYY-MM-DD")
    plan_preview.add_argument("--end-date", type=_iso_date, help="结束日期 YYYY-MM-DD")
    plan_preview.add_argument(
        "--browser-check",
        action="store_true",
        help="连接已登录的项目专用 Edge，只校验计划报表页面是否就绪",
    )
    plan_preview.add_argument(
        "--login-timeout", type=int, help="等待用户手动登录的秒数"
    )

    download = subparsers.add_parser("download", help="下载并归档五类报表")
    download.add_argument("--config", type=Path, help="JSON 配置文件路径")
    download.add_argument("--start-date", type=_iso_date, help="开始日期 YYYY-MM-DD")
    download.add_argument("--end-date", type=_iso_date, help="结束日期 YYYY-MM-DD")
    download.add_argument(
        "--reports",
        nargs="+",
        choices=REPORT_CHOICES,
        default=list(REPORT_CHOICES),
        help="需要下载的报表，默认全部",
    )
    download.add_argument("--output-dir", type=Path, help="本次输出根目录")
    download.add_argument("--resume-run", type=Path, help="续跑已有运行目录；不会重复提交已登记任务")

    merge = subparsers.add_parser("merge", help="将一次运行的五份 CSV 整理为新 Excel")
    merge.add_argument("--run-dir", type=Path, required=True, help="包含 extracted 的下载运行目录")
    merge.add_argument("--base-workbook", type=Path, required=True, help="含汇总公式和三张源表的底本工作簿")
    merge.add_argument("--start-date", type=_iso_date, help="开始日期；无运行清单时必填")
    merge.add_argument("--end-date", type=_iso_date, help="结束日期；无运行清单时必填")
    merge.add_argument("--output", type=Path, help="新 Excel 路径；默认保存在运行目录")

    tasks = subparsers.add_parser("download-tasks", help="只读查看下载任务管理列表")
    tasks.add_argument("--config", type=Path, help="JSON 配置文件路径")
    tasks.add_argument("--login-timeout", type=int, help="等待用户手动登录的秒数")
    subparsers.add_parser("gui", help="打开本地可视化工作台")
    return parser


def _validate_date_pair(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if (args.start_date is None) != (args.end_date is None):
        parser.error("--start-date 和 --end-date 必须同时提供")
    if args.start_date and args.start_date > args.end_date:
        parser.error("--start-date 不能晚于 --end-date")


def _check_environment(config_path: Path | None, browser_smoke: bool = False) -> int:
    config = load_config(config_path)
    try:
        playwright_version = metadata.version("playwright")
    except metadata.PackageNotFoundError:
        playwright_version = "未安装"

    print("配置检查通过")
    print(f"时区：{config.timezone}")
    print(f"浏览器通道：{config.browser.channel}")
    print(f"Playwright：{playwright_version}")
    print(f"输出目录：{config.paths.output}")
    print(f"日志目录：{config.paths.logs}")
    print(f"浏览器数据目录：{config.paths.browser_profile}")
    if browser_smoke:
        from marketing_calendar.browser import BrowserManager

        with BrowserManager(config):
            pass
        print("浏览器直连启动测试：通过")
    return EXIT_OK


def _inspect_pages(config_path: Path | None, login_timeout: int | None) -> int:
    from marketing_calendar.browser import BrowserManager
    from marketing_calendar.logging_setup import configure_logging
    from marketing_calendar.survey import survey_report_pages

    config = load_config(config_path)
    if login_timeout is not None and login_timeout <= 0:
        raise ConfigError("--login-timeout 必须是正整数")
    logger = configure_logging(config.paths.logs)
    with BrowserManager(config, logger, connect_existing=True) as browser:
        state = browser.wait_for_manual_login(login_timeout)
        if not state.logged_in:
            path = browser.save_failure_screenshot("manual_login_timeout")
            network_path = browser.save_network_diagnostics("login_network_failures")
            detail = f"；失败截图：{path}" if path else ""
            print(
                f"页面勘测停止：{state.reason}{detail}；网络诊断：{network_path}",
                file=sys.stderr,
            )
            return EXIT_FAILURE
        browser.open_report_page()
        result = survey_report_pages(browser.page, config)
        print(
            f"页面勘测结果：成功 {result.succeeded}，失败 {result.failed}；"
            f"报告：{result.path}"
        )
        return EXIT_OK if result.failed == 0 else EXIT_PARTIAL


def _preview_plan(args: argparse.Namespace) -> int:
    from marketing_calendar.browser import BrowserManager
    from marketing_calendar.logging_setup import configure_logging
    from marketing_calendar.plan_flow import build_plan_request, verify_plan_page

    config = load_config(args.config)
    date_range = ReportDateRange.resolve(
        args.start_date, args.end_date, timezone=config.timezone
    )
    request = build_plan_request(date_range)
    payload: dict[str, object] = {"request": request.as_dict()}
    if args.browser_check:
        if args.login_timeout is not None and args.login_timeout <= 0:
            raise ConfigError("--login-timeout 必须是正整数")
        logger = configure_logging(config.paths.logs)
        with BrowserManager(config, logger, connect_existing=True) as browser:
            state = browser.wait_for_manual_login(args.login_timeout)
            if not state.logged_in:
                raise BrowserError(f"计划报表页面校验停止：{state.reason}")
            readiness = verify_plan_page(browser.page, config, date_range)
            payload["page_readiness"] = readiness.__dict__
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return EXIT_OK


def _list_download_tasks(args: argparse.Namespace) -> int:
    from marketing_calendar.browser import BrowserManager
    from marketing_calendar.download_tasks import open_download_tasks, snapshot_download_tasks
    from marketing_calendar.logging_setup import configure_logging

    config = load_config(args.config)
    if args.login_timeout is not None and args.login_timeout <= 0:
        raise ConfigError("--login-timeout 必须是正整数")
    logger = configure_logging(config.paths.logs)
    with BrowserManager(config, logger, connect_existing=True) as browser:
        state = browser.wait_for_manual_login(args.login_timeout)
        if not state.logged_in:
            raise BrowserError(f"下载任务列表读取停止：{state.reason}")
        open_download_tasks(browser.page, config)
        tasks = snapshot_download_tasks(browser.page)
    print(
        json.dumps(
            {"task_count": len(tasks), "tasks": [task.as_dict() for task in tasks]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return EXIT_OK


def _download_reports(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from marketing_calendar.browser import BrowserManager
    from marketing_calendar.download_runner import prepare_run, run_download
    from marketing_calendar.logging_setup import configure_logging

    if args.resume_run is not None and (
        args.start_date is not None
        or args.end_date is not None
        or args.output_dir is not None
        or args.reports != list(REPORT_CHOICES)
    ):
        parser.error("--resume-run 不能同时指定日期、输出目录或报表；续跑使用原清单")
    config = load_config(args.config)
    date_range = ReportDateRange.resolve(
        args.start_date, args.end_date, timezone=config.timezone
    )
    logger = configure_logging(config.paths.logs)
    with BrowserManager(config, logger, connect_existing=True) as browser:
        state = browser.wait_for_manual_login()
        if not state.logged_in:
            raise BrowserError(f"下载流程停止：{state.reason}")
        archive, frozen_range, reports = prepare_run(
            args.output_dir or config.paths.output,
            date_range,
            args.reports,
            resume_run=args.resume_run,
        )
        print(f"运行目录：{archive.root}", flush=True)
        try:
            manifest = run_download(
                browser.page, config, archive, frozen_range, reports
            )
        except Exception:
            print(
                f"本次运行已暂停；可在人工核对后用 --resume-run {archive.root} 续跑。",
                file=sys.stderr,
            )
            raise
    print(f"五类报表归档清单：{manifest}")
    return EXIT_OK


def _merge_reports(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from marketing_calendar.data_merge import build_merged_workbook, prepare_merge

    _validate_date_pair(parser, args)
    run_dir = args.run_dir.resolve()
    csv_directory = run_dir / "extracted"
    if not csv_directory.is_dir():
        raise MergeError(f"运行目录缺少 extracted：{run_dir}")
    manifest_path = run_dir / "manifest.json"
    manifest_dates = None
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            period = manifest["date_range"]
            manifest_dates = (
                date.fromisoformat(period["start_date"]),
                date.fromisoformat(period["end_date"]),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MergeError(f"运行清单日期无效：{manifest_path}") from exc
    if args.start_date is None:
        if manifest_dates is None:
            parser.error("运行目录没有有效清单时，必须同时指定 --start-date 和 --end-date")
        start_date, end_date = manifest_dates
    else:
        start_date, end_date = args.start_date, args.end_date
        if manifest_dates is not None and (start_date, end_date) != manifest_dates:
            raise MergeError("指定日期与运行清单日期不一致")
    if start_date > end_date:
        parser.error("--start-date 不能晚于 --end-date")

    output = args.output or run_dir / f"万相台日报表_{end_date:%Y%m%d}_整理.xlsx"
    plan = prepare_merge(
        args.base_workbook,
        csv_directory,
        output,
        expected_start=start_date,
        expected_end=end_date,
    )
    print(
        f"输入校验通过：{start_date} 至 {end_date}；"
        f"主体 {plan.row_counts['subject']} 行，"
        f"人群 {plan.row_counts['audience']} 行，"
        f"关键词 {plan.row_counts['keyword']} 行",
        flush=True,
    )
    result = build_merged_workbook(plan, latest_date=end_date)
    print(f"整理完成：{result.resolve()}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return _check_environment(args.config, args.browser_smoke)

        if args.command == "inspect":
            return _inspect_pages(args.config, args.login_timeout)

        if args.command == "login":
            config = load_config(args.config)
            session = launch_manual_login_edge(config)
            print("项目专用 Edge 已启动，请在浏览器中手动完成登录。")
            print(f"会话启动时间：{session.launched_at}")
            return EXIT_OK

        if args.command == "plan-preview":
            return _preview_plan(args)

        if args.command == "download-tasks":
            return _list_download_tasks(args)

        if args.command == "download":
            _validate_date_pair(parser, args)
            return _download_reports(args, parser)

        if args.command == "merge":
            return _merge_reports(args, parser)

        if args.command == "gui":
            from marketing_calendar.frontend import launch

            launch()
            return EXIT_OK
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return EXIT_FAILURE
    except (
        BrowserError,
        SurveyError,
        EdgeSessionError,
        DateRangeError,
        DownloadTaskError,
        ArchiveError,
        DownloadRunError,
        ReportFilterError,
        PlanReportFlowError,
        ManualVerificationRequired,
        SubmissionUncertain,
        MergeError,
    ) as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return EXIT_FAILURE
    except KeyboardInterrupt:
        print("运行已由用户停止", file=sys.stderr)
        return 130

    parser.error(f"未知命令：{args.command}")
    return EXIT_FAILURE

