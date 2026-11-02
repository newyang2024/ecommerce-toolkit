# -*- coding: utf-8 -*-
"""桌面应用入口：双击启动，或通过"启动工具.bat"打开。"""
# 关键：必须在主线程、QApplication 创建之前完成以下导入。
# 1. threading 和 asyncio：否则 QThread 子线程第一次导入 threading 时，会把主线程
#    身份错误登记到子线程，导致 Playwright 在子线程报 set_wakeup_fd 错误。
# 2. onnxruntime：它的原生 DLL 必须在 QApplication 初始化前完成加载，否则在子线程
#    首次加载会报 DLL 初始化例程失败。
import threading  # noqa: F401
import asyncio  # noqa: F401
import onnxruntime  # noqa: F401
import sys
from pathlib import Path

# 确保能导入 core 和 ui（本文件在 05_程序 目录下）
PROGRAM_ROOT = Path(__file__).resolve().parent
if str(PROGRAM_ROOT) not in sys.path:
    sys.path.insert(0, str(PROGRAM_ROOT))


def main():
    import os
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    # 便携环境（复制到其他电脑）下，Qt 可能无法自动定位平台插件，
    # 这里按 PyQt5 包的实际位置显式指定插件路径，避免创建 QApplication 时崩溃。
    import PyQt5
    plugin_dir = Path(PyQt5.__file__).resolve().parent / "Qt5" / "plugins"
    if plugin_dir.exists():
        os.environ["QT_PLUGIN_PATH"] = str(plugin_dir)
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugin_dir / "platforms")

    # 高分屏清晰显示
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    from ui.app_style import APP_QSS
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
