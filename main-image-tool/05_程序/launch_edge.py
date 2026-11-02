# -*- coding: utf-8 -*-
"""启动带调试端口 9223 的专用浏览器（Edge 优先，Chrome 兜底），与日常浏览器互不影响。

Windows 和 macOS 都支持，按系统自动定位浏览器可执行文件。
"""
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

PROGRAM_ROOT = Path(__file__).resolve().parent
# 沿用原目录名，避免 Windows 老用户重新登录；macOS 同样使用该目录
PROFILE_DIR = PROGRAM_ROOT / "data" / "edge_cdp_profile"
PORT = 9223
HOME_URL = "https://www.tmall.com"


def _candidates():
    """返回当前系统下按优先级排列的浏览器可执行路径。"""
    if sys.platform == "win32":
        return [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    if sys.platform == "darwin":
        return [
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    # Linux
    return [
        "/usr/bin/microsoft-edge",
        "/usr/bin/microsoft-edge-stable",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]


def find_browser():
    """定位第一个真实存在的浏览器，找不到再用 PATH 里的命令兜底。"""
    for candidate in _candidates():
        if Path(candidate).exists():
            return candidate
    for name in ("msedge", "microsoft-edge", "google-chrome", "chrome",
                 "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def port_open(port):
    for host in ("127.0.0.1", "localhost"):
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            continue
    return False


def main():
    browser = find_browser()
    if not browser:
        print("没有找到 Edge 或 Chrome，请确认已安装后再试。")
        return
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    if port_open(PORT):
        print("调试端口 %d 已在监听，无需重复启动。" % PORT)
        return

    subprocess.Popen(
        [
            browser,
            "--remote-debugging-port=%d" % PORT,
            "--user-data-dir=%s" % PROFILE_DIR,
            "--no-first-run",
            "--no-default-browser-check",
            HOME_URL,
        ]
    )
    for _ in range(60):
        if port_open(PORT):
            time.sleep(1.5)
            print("专用浏览器已启动，调试端口 %d 就绪。" % PORT)
            return
        time.sleep(0.5)
    print("启动后调试端口仍未就绪，请检查。")


if __name__ == "__main__":
    main()
