"""从本机已安装的完整 Windows Python 制作不含业务数据的便携包。

在源码机运行；目标机无需安装 Python，但仍需 Edge 与桌面版 Excel。
此脚本不访问网络，也不读取浏览器配置、账号、工作簿或下载结果。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "营销日历工具_便携版"
REQUIRED_PACKAGES = {
    "playwright": "1.63.0",
    "pyee": "13.0.1",
    "greenlet": "3.5.6",
    "typing_extensions": "4.16.0",
    "tzdata": "2026.4",
}
SITE_ENTRIES = (
    "playwright",
    "playwright-1.63.0.dist-info",
    "pyee",
    "pyee-13.0.1.dist-info",
    "greenlet",
    "greenlet-3.5.6.dist-info",
    "typing_extensions.py",
    "typing_extensions-4.16.0.dist-info",
    "tzdata",
    "tzdata-2026.4.dist-info",
)
PROJECT_FILES = (
    "main.py",
    "requirements.txt",
    "pyproject.toml",
    "README.md",
    "迁移说明.md",
    "迁移说明_便携版.txt",
    "启动营销日历工具.bat",
    "config/config.example.json",
)


def _ignore_caches(_directory: str, names: list[str]) -> set[str]:
    return {
        name for name in names
        if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
    }


def _copy_project(target: Path) -> None:
    for name in PROJECT_FILES:
        source = PROJECT_ROOT / name
        if not source.is_file():
            raise RuntimeError(f"项目文件不存在：{source}")
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for folder in ("marketing_calendar", "tests"):
        shutil.copytree(
            PROJECT_ROOT / folder, target / folder, ignore=_ignore_caches
        )


def _copy_runtime(target: Path, python_home: Path) -> None:
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        raise RuntimeError("只能在 64 位 Windows Python 上制作此便携包")
    if sys.version_info[:3] != (3, 10, 11):
        raise RuntimeError("当前打包环境须为已验证的 Python 3.10.11")
    for package, expected in REQUIRED_PACKAGES.items():
        actual = importlib.metadata.version(package)
        if actual != expected:
            raise RuntimeError(f"{package} 版本为 {actual}，要求 {expected}")

    site = python_home / "Lib" / "site-packages"
    required = ("python.exe", "pythonw.exe", "python3.dll", "python310.dll",
                "LICENSE.txt", "DLLs", "Lib", "tcl", *SITE_ENTRIES)
    missing = [
        name for name in required
        if not (site / name if name in SITE_ENTRIES else python_home / name).exists()
    ]
    if missing:
        raise RuntimeError(f"运行时文件缺失：{', '.join(missing)}")

    target.mkdir()
    for name in ("python.exe", "pythonw.exe", "python3.dll", "python310.dll",
                 "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        source = python_home / name
        if source.is_file():
            shutil.copy2(source, target / name)
    shutil.copytree(python_home / "DLLs", target / "DLLs",
                    ignore=_ignore_caches)
    shutil.copytree(python_home / "tcl", target / "tcl")
    shutil.copytree(
        python_home / "Lib", target / "Lib",
        ignore=lambda directory, names: (
            _ignore_caches(directory, names)
            | ({"site-packages", "test", "ensurepip", "idlelib", "venv"}
               if Path(directory) == python_home / "Lib" else set())
        ),
    )
    packaged_site = target / "Lib" / "site-packages"
    packaged_site.mkdir()
    for name in SITE_ENTRIES:
        source = site / name
        destination = packaged_site / name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=_ignore_caches)
        else:
            shutil.copy2(source, destination)


def _run_check(root: Path, *arguments: str) -> None:
    executable = root / "runtime" / "python.exe"
    result = subprocess.run(
        [str(executable), *arguments],
        cwd=root, text=True, capture_output=True, timeout=120,
        errors="replace",
    )
    if result.returncode:
        raise RuntimeError(
            f"便携版检查失败：{' '.join(arguments)}\n"
            f"{result.stdout[-3000:]}\n{result.stderr[-3000:]}"
        )
    print(f"通过：{' '.join(arguments)}")


def build(output_dir: Path) -> tuple[Path, str]:
    python_home = Path(sys.base_prefix).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final = output_dir / f"{PACKAGE_NAME}_{timestamp}.zip"
    if final.exists():
        raise RuntimeError(f"目标文件已存在，拒绝覆盖：{final}")

    with tempfile.TemporaryDirectory(prefix="portable_", dir=output_dir) as temp:
        staged = Path(temp) / PACKAGE_NAME
        staged.mkdir()
        _copy_project(staged)
        _copy_runtime(staged / "runtime", python_home)
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT, text=True, capture_output=True, check=True,
        ).stdout.strip()
        (staged / "版本信息.txt").write_text(
            f"源码提交：{commit}\n"
            "内嵌 Python：3.10.11 x64（含 Tcl/Tk）\n"
            "Playwright：1.63.0\n"
            f"打包时间：{datetime.now():%Y-%m-%d %H:%M:%S}\n"
            "包内不含账号、登录态、业务底本、CSV 或本机配置。\n",
            encoding="utf-8",
        )
        _run_check(staged, "-c",
                   "import tkinter as tk; root=tk.Tk(); root.withdraw(); root.destroy()")
        _run_check(staged, "main.py", "check")
        _run_check(staged, "-m", "unittest", "discover", "-s", "tests", "-q")

        temporary_zip = output_dir / f"{final.name}.tmp"
        if temporary_zip.exists():
            raise RuntimeError(f"临时文件已存在，拒绝覆盖：{temporary_zip}")
        try:
            with ZipFile(temporary_zip, "w", compression=ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
                for source in staged.rglob("*"):
                    if source.is_file():
                        archive.write(source, source.relative_to(staged.parent))
            temporary_zip.replace(final)
        finally:
            if temporary_zip.exists():
                temporary_zip.unlink()
    digest = hashlib.sha256()
    with final.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    sha256 = digest.hexdigest()
    (output_dir / f"{final.name}.sha256.txt").write_text(
        f"{sha256}  {final.name}\n", encoding="ascii"
    )
    return final, sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=PROJECT_ROOT / "dist")
    args = parser.parse_args()
    path, sha256 = build(args.output_dir.resolve())
    print(json.dumps({
        "package": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
