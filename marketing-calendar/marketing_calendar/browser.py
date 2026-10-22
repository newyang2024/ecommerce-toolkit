from __future__ import annotations

import logging
import json
import os
import time
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from marketing_calendar.config import AppConfig
from marketing_calendar.edge_session import EdgeSessionError, load_edge_session


EXPECTED_PLAYWRIGHT_VERSION = "1.63.0"
LOGIN_URL_MARKERS = ("login", "signin", "passport", "member/login")
LOGIN_TEXT_MARKERS = ("请登录", "扫码登录", "密码登录", "账号登录")
AUTHENTICATED_PAGE_MARKERS = ("基础报表", "营销场景报表", "计划报表", "下载管理")


class BrowserError(RuntimeError):
    """浏览器启动、登录或页面访问失败。"""


@dataclass(frozen=True)
class LoginState:
    logged_in: bool
    reason: str


def installed_playwright_version() -> str:
    try:
        return metadata.version("playwright")
    except metadata.PackageNotFoundError as exc:
        raise BrowserError("未安装 Playwright，请先安装锁定依赖") from exc


def validate_playwright_version() -> str:
    version = installed_playwright_version()
    if version != EXPECTED_PLAYWRIGHT_VERSION:
        raise BrowserError(
            "Playwright 版本不匹配："
            f"当前 {version}，要求 {EXPECTED_PLAYWRIGHT_VERSION}"
        )
    return version


def detect_login_state(page: Any) -> LoginState:
    url = (page.url or "").lower()
    if any(marker in url for marker in LOGIN_URL_MARKERS):
        return LoginState(False, f"当前地址为登录页面：{page.url}")

    for marker in LOGIN_TEXT_MARKERS:
        try:
            if page.get_by_text(marker, exact=True).count() > 0:
                return LoginState(False, f"页面显示登录提示：{marker}")
        except Exception:
            continue

    if "one.alimama.com" not in url:
        return LoginState(False, f"尚未进入目标站点：{page.url}")

    if _has_visible_exact_text(page, "首页") and _has_visible_exact_text(page, "报表"):
        return LoginState(True, "已识别登录后的首页导航")

    for marker in AUTHENTICATED_PAGE_MARKERS:
        if _has_visible_exact_text(page, marker):
            return LoginState(True, f"已识别报表页面标识：{marker}")
    return LoginState(False, "目标站点尚未显示已登录的报表页面标识")


def _has_visible_exact_text(page: Any, text: str) -> bool:
    try:
        locator = page.get_by_text(text, exact=True)
        for index in range(locator.count()):
            if locator.nth(index).is_visible():
                return True
    except Exception:
        return False
    return False


class BrowserManager:
    """管理项目专用、可见、直连的 Edge 持久化会话。"""

    def __init__(
        self,
        config: AppConfig,
        logger: logging.Logger | None = None,
        connect_existing: bool = False,
    ):
        self.config = config
        self.logger = logger or logging.getLogger("marketing_calendar.browser")
        self._playwright = None
        self._cdp_browser = None
        self.connect_existing = connect_existing
        self.context = None
        self.page = None
        self.network_failures: list[dict[str, str]] = []

    def start(self):
        validate_playwright_version()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserError("无法导入 Playwright，请重新安装锁定依赖") from exc

        profile = self.config.paths.browser_profile
        profile.mkdir(parents=True, exist_ok=True)
        proxy_names = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}
        saved_proxy_values = {
            key: os.environ.pop(key)
            for key in list(os.environ)
            if key.upper() in proxy_names
        }
        try:
            self._playwright = sync_playwright().start()
        finally:
            os.environ.update(saved_proxy_values)

        if self.connect_existing:
            self._connect_existing_edge()
            return self.page

        try:
            self.context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                channel=self.config.browser.channel,
                headless=self.config.browser.headless,
                proxy={"server": "direct://"},
                args=["--no-proxy-server"],
                # 下载任务管理页需要由 Playwright 接收浏览器下载事件并把文件
                # 安全保存到本次运行目录；禁止接收会导致点击“下载”后始终超时。
                accept_downloads=True,
                locale="zh-CN",
                timezone_id=self.config.timezone,
                viewport={"width": 1440, "height": 900},
            )
        except Exception as exc:
            self._stop_playwright()
            raise BrowserError(
                "Edge 启动失败。请确认 Microsoft Edge 已安装，且项目专用浏览器"
                "数据目录未被其他进程占用；不要关闭用户日常 Edge。"
            ) from exc

        self.context.set_default_timeout(self.config.browser.timeout_ms)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.on("requestfailed", self._record_request_failure)
        self.logger.info("项目专用 Edge 已启动，网络模式为直连")
        return self.page

    def _connect_existing_edge(self) -> None:
        try:
            session = load_edge_session(self.config)
        except EdgeSessionError as exc:
            self._stop_playwright()
            raise BrowserError(str(exc)) from exc
        endpoint = f"http://localhost:{session.port}"
        try:
            self._cdp_browser = self._playwright.chromium.connect_over_cdp(endpoint)
        except Exception as exc:
            self._stop_playwright()
            raise BrowserError("无法连接项目专用 Edge，请重新运行 login 命令") from exc
        if not self._cdp_browser.contexts:
            self._stop_playwright()
            raise BrowserError("项目专用 Edge 没有可连接的浏览器上下文")
        self.context = self._cdp_browser.contexts[0]
        self.context.set_default_timeout(self.config.browser.timeout_ms)
        target_pages = [
            page for page in self.context.pages if "one.alimama.com" in page.url
        ]
        self.page = target_pages[0] if target_pages else self.context.new_page()
        self.page.on("requestfailed", self._record_request_failure)
        self.logger.info("已连接手动登录的项目专用 Edge")

    def open_report_page(self):
        if self.page is None:
            raise BrowserError("浏览器尚未启动")
        try:
            self.page.goto(
                self.config.site.report_url,
                wait_until="domcontentloaded",
                timeout=self.config.browser.timeout_ms * 2,
            )
        except Exception as exc:
            raise BrowserError(
                "目标页面访问失败。请确认当前电脑可以直连 one.alimama.com。"
            ) from exc
        return self.page

    def wait_for_manual_login(self, timeout_seconds: int | None = None) -> LoginState:
        if self.page is None:
            raise BrowserError("浏览器尚未启动")
        timeout = timeout_seconds or self.config.site.manual_login_timeout_seconds
        deadline = time.monotonic() + timeout
        last_state = detect_login_state(self.page)
        login_prompt_opened = False
        while time.monotonic() < deadline:
            last_state = detect_login_state(self.page)
            if last_state.logged_in:
                return last_state
            if not login_prompt_opened:
                login_prompt_opened = self.open_login_prompt()
            time.sleep(2)
        return LoginState(False, f"等待手动登录超时：{last_state.reason}")

    def open_login_prompt(self) -> bool:
        """只唤起登录界面，不填写凭据、不操作验证码或安全验证。"""
        if self.page is None:
            raise BrowserError("浏览器尚未启动")
        for text in ("立即登录", "登录"):
            locator = self.page.get_by_text(text, exact=True)
            for index in range(locator.count()):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible():
                        candidate.click()
                        self.logger.info("已唤起手动登录界面")
                        return True
                except Exception:
                    continue
        return False

    def save_network_diagnostics(self, name: str) -> Path:
        target_dir = self.config.paths.logs / "diagnostics"
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{name}.json"
        frames = []
        if self.page is not None:
            for frame in self.page.frames:
                frames.append(self._sanitize_url(frame.url))
        payload = {
            "page_url": self._sanitize_url(self.page.url if self.page else ""),
            "frames": frames,
            "network_failures": self.network_failures,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _record_request_failure(self, request) -> None:
        failure = request.failure or "unknown"
        item = {
            "method": request.method,
            "url": self._sanitize_url(request.url),
            "failure": str(failure),
        }
        if item not in self.network_failures:
            self.network_failures.append(item)

    @staticmethod
    def _sanitize_url(url: str) -> str:
        if not url:
            return ""
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    def save_failure_screenshot(self, name: str) -> Path | None:
        if self.page is None:
            return None
        target_dir = self.config.paths.logs / "diagnostics"
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in name if c.isalnum() or c in "-_") or "failure"
        path = target_dir / f"{safe_name}.png"
        try:
            self.page.screenshot(path=str(path), full_page=False)
        except Exception:
            self.logger.exception("失败截图保存失败")
            return None
        return path

    def close(self) -> None:
        try:
            if self.context is not None and not self.connect_existing:
                try:
                    self.context.close()
                except Exception:
                    self.logger.warning("浏览器连接已提前关闭")
        finally:
            self.context = None
            self.page = None
            self._cdp_browser = None
            self._stop_playwright()

    def _stop_playwright(self) -> None:
        if self._playwright is not None:
            try:
                self._playwright.stop()
            finally:
                self._playwright = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

