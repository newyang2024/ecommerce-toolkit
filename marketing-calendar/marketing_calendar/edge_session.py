from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

from marketing_calendar.config import AppConfig


PROXY_ENV_NAMES = {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}


class EdgeSessionError(RuntimeError):
    """项目专用 Edge 启动或连接信息无效。"""


@dataclass(frozen=True)
class EdgeSession:
    pid: int
    port: int
    launched_at: str
    profile_dir: str


def session_file(config: AppConfig) -> Path:
    return config.paths.browser_profile.parent / "browser_session.json"


def environment_without_proxy(source: Mapping[str, str] | None = None) -> dict[str, str]:
    values = dict(source if source is not None else os.environ)
    return {
        key: value
        for key, value in values.items()
        if key.lower() not in PROXY_ENV_NAMES
    }


def find_edge_executable() -> Path:
    found = shutil.which("msedge.exe") or shutil.which("msedge")
    if found:
        return Path(found)

    try:
        import winreg

        locations = (
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
        )
        for hive, key_path in locations:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, None)
                candidate = Path(value)
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
    except ImportError:
        pass

    for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
        root = os.environ.get(env_name)
        if root:
            candidate = Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if candidate.is_file():
                return candidate
    raise EdgeSessionError("未找到 Microsoft Edge，请确认浏览器已安装")


def allocate_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("localhost", 0))
        return int(server.getsockname()[1])


def is_local_port_open(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=timeout):
            return True
    except OSError:
        return False


def build_edge_command(
    executable: Path,
    profile_dir: Path,
    port: int,
    target_url: str,
) -> list[str]:
    return [
        str(executable),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-proxy-server",
        "--no-first-run",
        "--no-default-browser-check",
        target_url,
    ]


def launch_manual_login_edge(config: AppConfig) -> EdgeSession:
    existing = load_edge_session(config, require_open=False)
    if existing and is_local_port_open(existing.port):
        return existing

    executable = find_edge_executable()
    profile = config.paths.browser_profile
    profile.mkdir(parents=True, exist_ok=True)
    port = allocate_local_port()
    process = subprocess.Popen(
        build_edge_command(executable, profile, port, config.site.report_url),
        env=environment_without_proxy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise EdgeSessionError("项目专用 Edge 在本地调试端口就绪前已经退出")
        if is_local_port_open(port):
            break
        time.sleep(0.25)
    else:
        raise EdgeSessionError("项目专用 Edge 启动后，本地调试端口未在 30 秒内就绪")

    session = EdgeSession(
        pid=process.pid,
        port=port,
        launched_at=datetime.now(ZoneInfo(config.timezone)).isoformat(),
        profile_dir=str(profile),
    )
    target = session_file(config)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(session), ensure_ascii=False, indent=2), encoding="utf-8")
    return session


def load_edge_session(
    config: AppConfig,
    require_open: bool = True,
) -> EdgeSession | None:
    path = session_file(config)
    if not path.is_file():
        if require_open:
            raise EdgeSessionError("没有项目专用 Edge 会话，请先运行 login 命令")
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        session = EdgeSession(
            pid=int(raw["pid"]),
            port=int(raw["port"]),
            launched_at=str(raw["launched_at"]),
            profile_dir=str(raw["profile_dir"]),
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise EdgeSessionError("项目专用 Edge 会话文件无效") from exc
    if require_open and not is_local_port_open(session.port):
        raise EdgeSessionError("项目专用 Edge 已关闭，请重新运行 login 命令")
    return session

