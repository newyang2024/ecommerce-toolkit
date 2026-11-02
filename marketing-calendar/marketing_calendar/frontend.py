"""Windows 本地界面：只编排既有流程，不自行处理报表数据。"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from marketing_calendar.config import load_config
from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.frontend_service import (
    ProgressEvent,
    REPORTS,
    REPORT_LABELS,
    RunSummary,
    inspect_run,
    list_runs,
    run_pipeline,
)
from marketing_calendar.risk_guard import ManualVerificationRequired, SubmissionUncertain


BG = "#f6f7fb"
SIDEBAR = "#eef0f6"
CARD = "#ffffff"
TEXT = "#22263a"
MUTED = "#697184"
ACCENT = "#4656db"
BORDER = "#e2e5ee"
WARNING = "#a76608"


class FrontendApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("营销日历 · 工作台")
        self.root.geometry("1140x710")
        self.root.minsize(950, 620)
        self.root.configure(bg=BG)
        self.config = load_config()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.active_run: Path | None = None
        self.history: tuple[RunSummary, ...] = ()

        period = ReportDateRange.default_for(timezone=self.config.timezone)
        self.start_var = tk.StringVar(value=period.start.isoformat())
        self.end_var = tk.StringVar(value=period.end.isoformat())
        self.base_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(self.config.paths.output))
        self.headline_var = tk.StringVar(value="准备新任务")
        self.detail_var = tk.StringVar(value="先打开项目专用 Edge 并登录，再启动五表流程。")
        self.result_var = tk.StringVar(value="暂无本次结果")
        self.status_vars = {key: tk.StringVar(value="未开始") for key in REPORTS}
        self.status_vars["merge"] = tk.StringVar(value="未开始")
        self.progress_vars = {key: tk.DoubleVar(value=0) for key in (*REPORTS, "merge")}
        self.percent_vars = {key: tk.StringVar(value="0%") for key in (*REPORTS, "merge")}
        self.total_progress = tk.DoubleVar(value=0)
        self.total_percent = tk.StringVar(value="0%")
        self._build()
        self._refresh_history()
        self.root.after(120, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _label(self, parent: tk.Widget, text: str, *, size: int = 10, color: str = TEXT,
               weight: str = "normal", bg: str = CARD) -> tk.Label:
        return tk.Label(parent, text=text, fg=color, bg=bg, font=("Segoe UI", size, weight), anchor="w")

    def _button(self, parent: tk.Widget, text: str, action, *, primary: bool = False) -> tk.Button:
        return tk.Button(
            parent, text=text, command=action, relief="flat", cursor="hand2",
            bg=ACCENT if primary else "#e9ecf5", fg="white" if primary else TEXT,
            activebackground="#3545bd" if primary else "#dfe3ef",
            activeforeground="white" if primary else TEXT,
            font=("Segoe UI", 10, "bold"), padx=15, pady=8, bd=0,
        )

    def _card(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        frame.pack(fill="x", pady=(0, 14))
        return frame

    def _build(self) -> None:
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)
        side = tk.Frame(shell, bg=SIDEBAR, width=196)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        self._label(side, "✦  营销日历", size=15, weight="bold", bg=SIDEBAR).pack(fill="x", padx=20, pady=(27, 31))
        self._button(side, "新建任务", self._show_new).pack(fill="x", padx=14, pady=4)
        self._button(side, "历史运行", self._show_history).pack(fill="x", padx=14, pady=4)
        self._label(side, "本地运行 · 数据留在本机", size=9, color=MUTED, bg=SIDEBAR).pack(side="bottom", padx=17, pady=22)

        self.main = tk.Frame(shell, bg=BG)
        self.main.pack(side="left", fill="both", expand=True, padx=28, pady=23)
        header = tk.Frame(self.main, bg=BG)
        header.pack(fill="x", pady=(0, 19))
        self._label(header, "工作台", size=21, weight="bold", bg=BG).pack(side="left")
        self._label(header, "五表下载 · 数据整理 · 安全续跑", size=10, color=MUTED, bg=BG).pack(side="right")

        self.new_page = tk.Frame(self.main, bg=BG)
        self.history_page = tk.Frame(self.main, bg=BG)
        self._build_new_page()
        self._build_history_page()
        self._show_new()

    def _field(self, parent: tk.Widget, label: str, variable: tk.StringVar,
               *, browse: bool = False, width: int = 22) -> tk.Frame:
        box = tk.Frame(parent, bg=CARD)
        self._label(box, label, size=9, color=MUTED).pack(anchor="w", pady=(0, 5))
        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x")
        entry = tk.Entry(row, textvariable=variable, relief="solid", bd=1,
                         highlightthickness=0, width=width, font=("Segoe UI", 10))
        entry.pack(side="left", fill="x", expand=True, ipady=5)
        if browse:
            self._button(row, "选择", lambda: self._choose_file(variable)).pack(side="left", padx=(8, 0))
        return box

    def _build_new_page(self) -> None:
        canvas = tk.Canvas(self.new_page, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.new_page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        content = tk.Frame(canvas, bg=BG)
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units"))
        settings = self._card(content)
        inner = tk.Frame(settings, bg=CARD)
        inner.pack(fill="x", padx=21, pady=17)
        self._label(inner, "本次任务", size=13, weight="bold").pack(anchor="w", pady=(0, 11))
        dates = tk.Frame(inner, bg=CARD)
        dates.pack(fill="x", pady=(0, 12))
        self._field(dates, "开始日期 · YYYY-MM-DD", self.start_var, width=18).pack(side="left", fill="x", expand=True, padx=(0, 14))
        self._field(dates, "结束日期 · YYYY-MM-DD", self.end_var, width=18).pack(side="left", fill="x", expand=True, padx=(0, 12))
        self._button(dates, "默认日期", self._apply_default_dates).pack(side="left", pady=(17, 0))
        self._field(inner, "日报表底本 · 只读输入", self.base_var, browse=True, width=65).pack(fill="x", pady=(0, 11))
        self._field(inner, "输出根目录", self.output_var, width=65).pack(fill="x")
        actions = tk.Frame(inner, bg=CARD)
        actions.pack(fill="x", pady=(13, 0))
        self.login_button = self._button(actions, "打开登录浏览器", self._launch_login)
        self.login_button.pack(side="left", padx=(0, 9))
        self.start_button = self._button(actions, "开始五表流程", self._start_new, primary=True)
        self.start_button.pack(side="left")
        self.resume_button = self._button(actions, "继续当前任务", self._resume)
        self.resume_button.pack(side="left", padx=9)
        self.resume_button.configure(state="disabled")

        progress = self._card(content)
        body = tk.Frame(progress, bg=CARD)
        body.pack(fill="x", padx=21, pady=15)
        tk.Label(body, textvariable=self.headline_var, fg=TEXT, bg=CARD,
                 font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x")
        tk.Label(body, textvariable=self.detail_var, fg=MUTED, bg=CARD,
                 font=("Segoe UI", 9), anchor="w", wraplength=700, justify="left").pack(fill="x", pady=(3, 11))
        total_line = tk.Frame(body, bg=CARD)
        total_line.pack(fill="x", pady=(0, 8))
        self._label(total_line, "总进度", size=9, weight="bold").pack(side="left", padx=(0, 9))
        ttk.Progressbar(total_line, variable=self.total_progress, maximum=100).pack(
            side="left", fill="x", expand=True
        )
        tk.Label(total_line, textvariable=self.total_percent, fg=ACCENT, bg=CARD,
                 font=("Segoe UI", 9, "bold"), width=5, anchor="e").pack(side="left", padx=(8, 0))
        grid = tk.Frame(body, bg=CARD)
        grid.pack(fill="x")
        for index, key in enumerate((*REPORTS, "merge")):
            box = tk.Frame(grid, bg="#f7f8fc", padx=9, pady=8)
            box.grid(row=index // 3, column=index % 3, sticky="ew", padx=4, pady=4)
            grid.grid_columnconfigure(index % 3, weight=1)
            self._label(box, REPORT_LABELS.get(key, "整理 Excel"), size=9, bg="#f7f8fc").pack(anchor="w")
            status_line = tk.Frame(box, bg="#f7f8fc")
            status_line.pack(fill="x", pady=(3, 3))
            tk.Label(status_line, textvariable=self.status_vars[key], fg=ACCENT, bg="#f7f8fc",
                     font=("Segoe UI", 9, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(status_line, textvariable=self.percent_vars[key], fg=MUTED, bg="#f7f8fc",
                     font=("Segoe UI", 9), anchor="e").pack(side="right")
            ttk.Progressbar(box, variable=self.progress_vars[key], maximum=100).pack(fill="x")
        self._label(body, "阶段记录", size=9, color=MUTED).pack(anchor="w", pady=(13, 4))
        self.log = tk.Text(body, height=5, bg="#f8f9fc", fg=TEXT, relief="flat",
                           font=("Consolas", 9), wrap="word", state="disabled")
        self.log.pack(fill="x")

        result = self._card(content)
        rbody = tk.Frame(result, bg=CARD)
        rbody.pack(fill="x", padx=21, pady=13)
        self._label(rbody, "结果", size=12, weight="bold").pack(anchor="w")
        tk.Label(rbody, textvariable=self.result_var, fg=MUTED, bg=CARD,
                 font=("Segoe UI", 9), anchor="w", wraplength=730, justify="left").pack(fill="x", pady=(4, 9))
        self.open_folder_button = self._button(rbody, "打开结果文件夹", self._open_folder)
        self.open_folder_button.pack(side="left")
        self.open_excel_button = self._button(rbody, "打开完整 Excel", self._open_workbook)
        self.open_excel_button.pack(side="left", padx=8)
        self.open_folder_button.configure(state="disabled")
        self.open_excel_button.configure(state="disabled")

    def _build_history_page(self) -> None:
        card = self._card(self.history_page)
        body = tk.Frame(card, bg=CARD)
        body.pack(fill="both", expand=True, padx=21, pady=18)
        self._label(body, "历史运行", size=13, weight="bold").pack(anchor="w", pady=(0, 10))
        self.history_list = tk.Listbox(body, font=("Segoe UI", 10), height=17,
                                       bg="#fafbfe", fg=TEXT, relief="solid", bd=1,
                                       selectbackground=ACCENT, selectforeground="white")
        self.history_list.pack(fill="both", expand=True)
        self.history_list.bind("<<ListboxSelect>>", self._history_selected)
        actions = tk.Frame(body, bg=CARD)
        actions.pack(fill="x", pady=(12, 0))
        self._button(actions, "刷新列表", self._refresh_history).pack(side="left")
        self._button(actions, "查看该任务", self._view_selected).pack(side="left", padx=8)
        self._button(actions, "继续该任务", self._resume_selected, primary=True).pack(side="left")
        self.history_info = tk.StringVar(value="选择一条运行记录查看详情。")
        tk.Label(body, textvariable=self.history_info, bg=CARD, fg=MUTED,
                 wraplength=690, justify="left", anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=(12, 0))

    def _show_new(self) -> None:
        self.history_page.pack_forget()
        self.new_page.pack(fill="both", expand=True)

    def _show_history(self) -> None:
        self.new_page.pack_forget()
        self._refresh_history()
        self.history_page.pack(fill="both", expand=True)

    def _choose_file(self, variable: tk.StringVar) -> None:
        selected = filedialog.askopenfilename(filetypes=[("Excel 工作簿", "*.xlsx"), ("所有文件", "*.*")])
        if selected:
            variable.set(selected)

    def _apply_default_dates(self) -> None:
        """恢复约定的“上月 1 日至昨天”默认日期，尚未启动的任务才可调整。"""
        period = ReportDateRange.default_for(timezone=self.config.timezone)
        self.start_var.set(period.start.isoformat())
        self.end_var.set(period.end.isoformat())
        self.detail_var.set(
            f"已填入默认日期：{period.start.isoformat()} 至 {period.end.isoformat()}（最新可用日期）。"
        )

    def _parse_paths(self) -> tuple[Path, Path]:
        base = Path(self.base_var.get().strip()).resolve()
        output = Path(self.output_var.get().strip()).resolve()
        if not base.is_file() or base.suffix.lower() != ".xlsx":
            raise ValueError("请选择有效的日报表底本 .xlsx 文件")
        if not self.output_var.get().strip():
            raise ValueError("请输入输出目录")
        return base, output

    def _parse_inputs(self) -> tuple[date, date, Path, Path]:
        start = date.fromisoformat(self.start_var.get().strip())
        end = date.fromisoformat(self.end_var.get().strip())
        if start > end:
            raise ValueError("开始日期不能晚于结束日期")
        base, output = self._parse_paths()
        return start, end, base, output

    def _start_worker(self, target) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("任务正在运行", "请等待当前步骤结束，避免重复启动。")
            return
        self.start_button.configure(state="disabled")
        self.resume_button.configure(state="disabled")
        self.worker = threading.Thread(target=target, daemon=False)
        self.worker.start()

    def _start_new(self) -> None:
        try:
            start, end, base, output = self._parse_inputs()
        except ValueError as exc:
            messagebox.showerror("输入需要检查", str(exc))
            return
        existing = [
            item for item in list_runs(output)
            if item.start_date == start.isoformat() and item.end_date == end.isoformat()
            and set(item.planned) == set(REPORTS)
        ]
        unfinished = next((item for item in existing if not item.is_download_complete or not item.workbook), None)
        if unfinished is not None:
            self.active_run = unfinished.run_dir
            self._show_summary(unfinished)
            self.headline_var.set("发现同日期未完成任务")
            self.detail_var.set("已载入原运行记录。请点击“继续当前任务”，避免重复提交。")
            self.resume_button.configure(state="normal")
            return
        if existing and not messagebox.askyesno(
            "同日期已有结果",
            "该日期范围已有完整运行结果。重新运行会在网站创建新的五表任务。确定继续吗？",
        ):
            return
        self.active_run = None
        for status in self.status_vars.values():
            status.set("未开始")
        self._reset_progress()
        self.headline_var.set("正在启动任务")
        self.detail_var.set(f"日期已冻结：{start} 至 {end}")
        self._start_worker(lambda: self._run_task(base, output, start, end, None))

    def _resume(self) -> None:
        if self.active_run is None:
            return
        try:
            base, output = self._parse_paths()
        except ValueError as exc:
            messagebox.showerror("输入需要检查", str(exc))
            return
        self._start_worker(lambda: self._run_task(base, output, None, None, self.active_run))

    def _run_task(self, base: Path, output: Path,
                  start: date | None, end: date | None, resume: Path | None) -> None:
        try:
            result = run_pipeline(
                base_workbook=base, output_root=output,
                start_date=start, end_date=end, resume_run=resume, config=self.config,
                emit=lambda event: self.events.put(("progress", event)),
            )
            self.events.put(("done", result))
        except Exception as exc:
            self.events.put(("error", exc))

    def _launch_login(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("任务正在运行", "请先在已打开的项目专用 Edge 中操作。")
            return
        try:
            from marketing_calendar.edge_session import launch_manual_login_edge
            launch_manual_login_edge(self.config)
            self._append_log("已打开项目专用 Edge；请在浏览器中手动登录。")
            self.detail_var.set("登录完成后，回到这里点击“开始五表流程”。")
        except Exception as exc:
            messagebox.showerror("浏览器未启动", str(exc))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    self._on_progress(payload)
                elif kind == "done":
                    self._on_done(payload)
                elif kind == "error":
                    self._on_error(payload)
        except queue.Empty:
            pass
        self.root.after(120, self._drain_events)

    def _on_progress(self, event: ProgressEvent) -> None:
        if event.run_dir is not None:
            self.active_run = event.run_dir
            self.open_folder_button.configure(state="normal")
        if event.report_key in self.status_vars:
            names = {
                "checking": "检查中", "filtering": "筛选设置", "submitting": "提交任务",
                "confirming": "核对任务", "queued": "任务已确认", "waiting": "平台生成等待",
                "downloading": "下载校验",
                "complete": "已完成",
            }
            self.status_vars[event.report_key].set(names.get(event.phase, event.phase))
            checkpoints = {
                "checking": 0, "filtering": 10, "submitting": 25, "confirming": 40,
                "queued": 45, "waiting": 50, "downloading": 65, "complete": 100,
            }
            self._set_progress(event.report_key, checkpoints.get(event.phase))
        if event.phase in {"merge_check", "merging", "complete"} and event.report_key is None:
            self.status_vars["merge"].set(
                "已完成" if event.phase == "complete" else
                "校验输入" if event.phase == "merge_check" else "整理中"
            )
            if event.phase == "merge_check":
                self._set_progress("merge", 0)
            elif event.phase == "merging" and event.percent is not None:
                self._set_progress("merge", event.percent)
            elif event.phase == "complete":
                self._set_progress("merge", 100)
        finished = event.phase == "complete" and event.report_key is None
        self.headline_var.set("任务完成" if finished else "正在运行")
        self.detail_var.set(event.message)
        self._append_log((REPORT_LABELS.get(event.report_key, "流程") + " · " + event.message))

    def _on_done(self, summary: RunSummary) -> None:
        self.active_run = summary.run_dir
        self.start_button.configure(state="normal")
        self.resume_button.configure(state="normal")
        self.headline_var.set("任务完成")
        self.detail_var.set("五张报表已处理，结果保存在独立运行目录。")
        self._show_summary(summary)
        self._refresh_total_progress()
        self._refresh_history()

    def _on_error(self, error: Exception) -> None:
        self.start_button.configure(state="normal")
        self.resume_button.configure(state="normal" if self.active_run else "disabled")
        paused = isinstance(error, (ManualVerificationRequired, SubmissionUncertain))
        self.headline_var.set("等待人工核对" if paused else "任务暂停")
        self.detail_var.set(str(error))
        self._append_log("暂停 · " + str(error))
        if self.active_run is not None:
            try:
                self._show_summary(inspect_run(self.active_run))
            except ValueError:
                pass
        self._refresh_history()

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _reset_progress(self) -> None:
        for key in self.progress_vars:
            self.progress_vars[key].set(0)
            self.percent_vars[key].set("0%")
        self._refresh_total_progress()

    def _set_progress(self, key: str, value: int | None) -> None:
        if value is None or key not in self.progress_vars:
            return
        current = self.progress_vars[key].get()
        value = max(int(current), min(100, max(0, int(value))))
        self.progress_vars[key].set(value)
        self.percent_vars[key].set(f"{value}%")
        self._refresh_total_progress()

    def _refresh_total_progress(self) -> None:
        value = sum(variable.get() for variable in self.progress_vars.values()) / len(self.progress_vars)
        self.total_progress.set(value)
        self.total_percent.set(f"{int(value)}%")

    def _show_summary(self, summary: RunSummary) -> None:
        for key in REPORTS:
            self.status_vars[key].set("已完成" if key in summary.completed else "未完成")
            self._set_progress(key, 100 if key in summary.completed else 0)
        self.status_vars["merge"].set("已生成" if summary.workbook else "待整理")
        self._set_progress("merge", 100 if summary.workbook else 0)
        counts = " · ".join(
            f"{REPORT_LABELS[key]} {summary.row_counts[key]:,} 行"
            for key in REPORTS if key in summary.row_counts
        )
        workbook_text = (
            f"Excel 已生成（{summary.workbook_bytes / 1024 / 1024:.1f} MB）；"
            if summary.workbook_bytes is not None else "Excel 尚未生成；"
        )
        self.result_var.set(
            f"{summary.start_date} 至 {summary.end_date} · 五表完成 {len(set(summary.completed))}/{len(summary.planned)}\n"
            f"{counts}\n{workbook_text}透视缓存刷新状态需单独核验。"
        )
        self.open_folder_button.configure(state="normal")
        self.open_excel_button.configure(state="normal" if summary.workbook else "disabled")

    def _refresh_history(self) -> None:
        self.history = list_runs(Path(self.output_var.get().strip() or self.config.paths.output))
        self.history_list.delete(0, "end")
        for item in self.history:
            state = "完整结果" if item.workbook else ("待整理" if item.is_download_complete else "未完成")
            self.history_list.insert("end", f"{item.end_date}  ·  {state}  ·  {item.run_dir.name}")

    def _selected_summary(self) -> RunSummary | None:
        selection = self.history_list.curselection()
        return self.history[selection[0]] if selection else None

    def _history_selected(self, _event=None) -> None:
        summary = self._selected_summary()
        if summary:
            self.history_info.set(
                f"{summary.start_date} 至 {summary.end_date} · 已完成 {len(set(summary.completed))}/{len(summary.planned)} 张报表\n"
                f"目录：{summary.run_dir}"
            )

    def _view_selected(self) -> None:
        summary = self._selected_summary()
        if summary:
            self.active_run = summary.run_dir
            self._show_new()
            self._show_summary(summary)
            self.headline_var.set("历史运行")
            self.detail_var.set("当前显示已有记录；如未完成，可点击“继续当前任务”。")
            self.resume_button.configure(state="normal")

    def _resume_selected(self) -> None:
        self._view_selected()
        if self.active_run:
            self._resume()

    def _open_folder(self) -> None:
        if self.active_run and self.active_run.is_dir():
            os.startfile(str(self.active_run))

    def _open_workbook(self) -> None:
        if self.active_run:
            summary = inspect_run(self.active_run)
            if summary.workbook:
                os.startfile(str(summary.workbook))

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("任务仍在运行", "当前步骤尚未结束。为避免中断下载或整理，请先让任务完成；窗口可以最小化。")
            return
        self.root.destroy()


def launch() -> None:
    root = tk.Tk()
    FrontendApp(root)
    root.mainloop()
