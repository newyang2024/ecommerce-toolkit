from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigError(ValueError):
    """配置文件无效。"""


@dataclass(frozen=True)
class PathConfig:
    output: Path
    logs: Path
    browser_profile: Path


@dataclass(frozen=True)
class BrowserConfig:
    channel: str
    headless: bool
    timeout_ms: int


@dataclass(frozen=True)
class SiteConfig:
    report_url: str
    manual_login_timeout_seconds: int


@dataclass(frozen=True)
class DownloadConfig:
    poll_interval_seconds: int
    timeout_seconds: int
    max_uncompressed_bytes: int


@dataclass(frozen=True)
class AppConfig:
    timezone: str
    paths: PathConfig
    browser: BrowserConfig
    site: SiteConfig
    download: DownloadConfig


DEFAULT_CONFIG: dict[str, Any] = {
    "timezone": "Asia/Shanghai",
    "paths": {
        "output": "output",
        "logs": "logs",
        "browser_profile": "data/browser_profile",
    },
    "browser": {
        "channel": "msedge",
        "headless": False,
        "timeout_ms": 30_000,
    },
    "site": {
        "report_url": "https://one.alimama.com/index.html#/report/campaign",
        "manual_login_timeout_seconds": 600,
    },
    "download": {
        "poll_interval_seconds": 3,
        "timeout_seconds": 600,
        "max_uncompressed_bytes": 1_073_741_824,
    },
}

_FORBIDDEN_CONFIG_KEYS = {
    "proxy",
    "proxies",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
}


def _merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _reject_proxy_settings(value: Any, location: str = "config") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_CONFIG_KEYS:
                raise ConfigError(f"{location} 不允许配置代理字段：{key}")
            _reject_proxy_settings(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_proxy_settings(child, f"{location}[{index}]")


def _resolve_project_path(value: Any, name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"paths.{name} 必须是非空字符串")
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{name} 必须是正整数")
    return value


def load_config(path: str | Path | None = None) -> AppConfig:
    raw: dict[str, Any] = {}
    if path is not None:
        config_path = Path(path)
        if not config_path.is_file():
            raise ConfigError(f"配置文件不存在：{config_path}")
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"配置文件读取失败：{exc}") from exc
        if not isinstance(loaded, dict):
            raise ConfigError("配置文件根节点必须是 JSON 对象")
        raw = loaded

    _reject_proxy_settings(raw)
    values = _merge(DEFAULT_CONFIG, raw)

    timezone = values.get("timezone")
    if timezone != "Asia/Shanghai":
        raise ConfigError("timezone 必须为 Asia/Shanghai")

    paths = values["paths"]
    browser = values["browser"]
    site = values["site"]
    download = values["download"]

    channel = browser.get("channel")
    if channel != "msedge":
        raise ConfigError("browser.channel 必须为 msedge")
    headless = browser.get("headless")
    if not isinstance(headless, bool):
        raise ConfigError("browser.headless 必须是布尔值")

    report_url = site.get("report_url")
    if not isinstance(report_url, str) or not report_url.startswith(
        "https://one.alimama.com/"
    ):
        raise ConfigError("site.report_url 必须是 one.alimama.com 的 HTTPS 地址")

    return AppConfig(
        timezone=timezone,
        paths=PathConfig(
            output=_resolve_project_path(paths.get("output"), "output"),
            logs=_resolve_project_path(paths.get("logs"), "logs"),
            browser_profile=_resolve_project_path(
                paths.get("browser_profile"), "browser_profile"
            ),
        ),
        browser=BrowserConfig(
            channel=channel,
            headless=headless,
            timeout_ms=_positive_int(browser.get("timeout_ms"), "browser.timeout_ms"),
        ),
        site=SiteConfig(
            report_url=report_url,
            manual_login_timeout_seconds=_positive_int(
                site.get("manual_login_timeout_seconds"),
                "site.manual_login_timeout_seconds",
            ),
        ),
        download=DownloadConfig(
            poll_interval_seconds=_positive_int(
                download.get("poll_interval_seconds"),
                "download.poll_interval_seconds",
            ),
            timeout_seconds=_positive_int(
                download.get("timeout_seconds"), "download.timeout_seconds"
            ),
            max_uncompressed_bytes=_positive_int(
                download.get("max_uncompressed_bytes"),
                "download.max_uncompressed_bytes",
            ),
        ),
    )

