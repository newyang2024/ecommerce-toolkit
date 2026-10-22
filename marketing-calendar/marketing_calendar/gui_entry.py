"""图形工作台的独立启动入口：启动失败时保留本地诊断，而非静默退出。"""

from __future__ import annotations

import traceback
from pathlib import Path


def main() -> int:
    try:
        from marketing_calendar.frontend import launch

        launch()
        return 0
    except Exception:
        log_path = Path(__file__).resolve().parents[1] / "logs" / "gui_startup_error.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "营销日历工作台未启动",
                f"启动失败，错误详情已保存到：\n{log_path}",
                parent=root,
            )
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
