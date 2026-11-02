# -*- coding: utf-8 -*-
"""跨平台的系统能力封装，避免在业务代码里直接写 Windows 专属调用。"""
import subprocess
import sys


def open_in_system(path) -> None:
    """用操作系统默认方式打开文件或文件夹。

    Windows 用 os.startfile，macOS 用 open，Linux 用 xdg-open。
    """
    target = str(path)
    if sys.platform == "win32":
        import os

        os.startfile(target)
        return
    if sys.platform == "darwin":
        cmd = ["open", target]
    else:
        cmd = ["xdg-open", target]
    subprocess.Popen(cmd)
