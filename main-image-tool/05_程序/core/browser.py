# -*- coding: utf-8 -*-
"""浏览器管理：通过 CDP 连接手动登录的真实 Edge，含反检测和拟人操作。"""
import os
import random
import socket
import time
from urllib.parse import urlparse


def _ensure_localhost_noproxy():
    """连本地调试端口前强制绕过代理。

    本机开代理时，Playwright 连 127.0.0.1:9223 会被发到代理导致 socket hang up。
    必须在 import playwright 之前执行。
    """
    add = ["127.0.0.1", "localhost"]
    for var in ("NO_PROXY", "no_proxy"):
        items = [x for x in os.environ.get(var, "").split(",") if x]
        for a in add:
            if a not in items:
                items.append(a)
        os.environ[var] = ",".join(items)


_ensure_localhost_noproxy()

from playwright.sync_api import sync_playwright  # noqa: E402

from .config_loader import load_config
from .logger import get_logger

logger = get_logger("browser")


class BrowserManager:
    """连接真实浏览器，不自动关闭用户窗口。"""

    def __init__(self):
        self.config = load_config()
        self.browser_cfg = self.config["browser"]
        self.humanize_cfg = self.config["humanize"]
        self.playwright = None
        self.cdp_browser = None
        self.context = None
        self.page = None

    def start(self):
        """连接浏览器，返回一个可用页面。"""
        self.playwright = sync_playwright().start()
        cdp_url = self.browser_cfg["cdp_url"]
        port = urlparse(cdp_url).port or 9223

        if not self._port_open(port):
            raise RuntimeError(
                "没有检测到浏览器调试端口（%s）。请先用启动脚本打开带调试端口的 Edge，"
                "确认天猫已登录并保持窗口开着，再运行。" % cdp_url
            )

        try:
            self.cdp_browser = self.playwright.chromium.connect_over_cdp(cdp_url)
        except Exception as e:
            raise RuntimeError("连接浏览器调试端口失败（%s），原始错误：%s" % (cdp_url, e))

        if self.cdp_browser.contexts:
            self.context = self.cdp_browser.contexts[0]
        else:
            self.context = self.cdp_browser.new_context()

        self._inject_stealth()
        self.context.set_default_timeout(self.browser_cfg["new_page_timeout"] * 1000)

        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()
        logger.info("已通过 CDP 连接到真实浏览器")
        return self.page

    def new_page(self):
        """开一个新页面用于采集。"""
        page = self.context.new_page()
        return page

    def close_page(self, page):
        """关闭采集页面，不动其他页面。"""
        try:
            page.close()
        except Exception as e:
            logger.warning("关闭页面异常: %s" % e)

    def _port_open(self, port):
        for host in ("127.0.0.1", "localhost"):
            try:
                with socket.create_connection((host, port), timeout=1):
                    return True
            except OSError:
                continue
        return False

    def _inject_stealth(self):
        """注入反检测脚本，隐藏自动化特征。"""
        stealth_js = """
        () => {
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters);
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 16 });
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.call(this, parameter);
            };
        }
        """
        self.context.add_init_script("(%s)()" % stealth_js)
        logger.info("反检测脚本已注入")

    def human_delay(self, key: str = "action_delay"):
        """按配置的区间随机等待。"""
        lo, hi = self.humanize_cfg.get(key, [0.5, 1.0])
        time.sleep(random.uniform(lo, hi))

    def human_move_mouse(self, page=None):
        """随机移动鼠标，模拟真人轨迹。"""
        page = page or self.page
        for _ in range(random.randint(1, 3)):
            x = random.randint(100, 1300)
            y = random.randint(100, 800)
            page.mouse.move(x, y, steps=random.randint(10, 25))
            time.sleep(random.uniform(0.05, 0.2))

    def close(self):
        """只断开 CDP 连接，用户手动打开的浏览器保持运行。"""
        try:
            if self.cdp_browser:
                self.cdp_browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("已断开连接，浏览器窗口保持打开")
        except Exception as e:
            logger.error("关闭连接异常: %s" % e)
        finally:
            self.page = None
            self.context = None
            self.cdp_browser = None
            self.playwright = None
