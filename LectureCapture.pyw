#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LectureCapture —— 课程字幕抓取（图形界面）
==========================================
双击 LectureCapture.cmd 即可打开面板；直接打开本文件也会切换到项目环境。

依赖同目录的 capture.py 作为抓取引擎。
"""

import json
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    from bootstrap import ensure_project_python
    if ensure_project_python():
        raise SystemExit(0)

import tkinter as tk
from tkinter import filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture as core

HERE = Path(__file__).resolve().parent
SETTINGS = HERE / "settings.json"
F_DISPLAY = ("Segoe UI Variable Display", 22, "bold")
F_TITLE = ("Microsoft YaHei UI", 12, "bold")
F = ("Microsoft YaHei UI", 10)
F_SMALL = ("Microsoft YaHei UI", 9)
F_BOLD = ("Microsoft YaHei UI", 10, "bold")
F_MONO = ("Consolas", 10)
F_BIG = ("Microsoft YaHei UI", 11, "bold")

BG = "#F4F7FB"
CARD = "#FFFFFF"
TEXT = "#172033"
MUTED = "#667085"
BORDER = "#DDE4EE"
BLUE = "#2563EB"
BLUE_HOVER = "#1D4ED8"
BLUE_SOFT = "#EAF1FF"
GREEN = "#15803D"
GREEN_SOFT = "#EAF8EF"
RED = "#DC2626"
RED_HOVER = "#B91C1C"
RED_SOFT = "#FDECEC"
AMBER = "#B45309"
AMBER_SOFT = "#FFF5E5"
GREY = "#7B8798"


class App:
    def __init__(self, root):
        self.root = root
        self.engine = None
        self.tick_job = None
        self.running = False
        self.saved_paths = None

        root.title("Lecture Capture — 课程字幕抓取")
        root.geometry("780x820")
        root.minsize(460, 360)
        root.configure(bg=BG)

        cfg = self._load_settings()
        self.var_out = tk.StringVar(value=cfg.get("out") or str(Path(core.default_out_dir()) / "LectureScripts"))
        self.var_name = tk.StringVar(value=cfg.get("name", ""))
        self.var_app = tk.StringVar(value=cfg.get("app", "msedge"))
        self.var_mode = tk.StringVar(value=cfg.get("mode", core.MODE_VIDEO))
        if self.var_mode.get() not in core.CAPTURE_MODES:
            self.var_mode.set(core.MODE_VIDEO)

        self._build()
        self.var_name.trace_add("write", lambda *_: self._refresh_start_label())
        self.var_out.trace_add("write", lambda *_: self._refresh_start_label())
        self._refresh_start_label()
        # 先起时间线线程，1.5 秒后再做一次预检（SMTC 需要一点时间才有数据）
        self._boot_timeline()
        root.after(1600, self._precheck)

    # ------------------------------------------------------------------ 配置
    def _load_settings(self):
        try:
            return json.loads(SETTINGS.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_settings(self):
        try:
            SETTINGS.write_text(json.dumps({
                "out": self.var_out.get().strip(),
                "name": self.var_name.get().strip(),
                "app": self.var_app.get().strip() or "msedge",
                "mode": self.var_mode.get(),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------ 界面
    def _build(self):
        root = self.root
        shell = tk.Frame(root, bg=BG)
        shell.pack(fill="both", expand=True, padx=20, pady=(16, 14))
        controls = tk.Frame(shell, bg=BG)
        controls.pack(side="bottom", fill="x", pady=(12, 0))
        viewport = tk.Frame(shell, bg=BG)
        viewport.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(viewport, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(viewport, orient="vertical", command=self._scroll_view)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        outer = self.content = tk.Frame(self.canvas, bg=BG)
        self.content_window = self.canvas.create_window((0, 0), window=outer, anchor="nw")
        self.layout_job = None
        self.compact = None
        self.status_tiles = []

        # ---- 页头 ----
        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x", pady=(0, 16))
        mark = tk.Label(header, text="LC", font=("Segoe UI Variable Display", 13, "bold"),
                        bg=BLUE, fg="white", width=3, height=2)
        mark.pack(side="left", padx=(0, 12))
        heading = tk.Frame(header, bg=BG)
        heading.pack(side="left", fill="x", expand=True)
        self.l_heading = tk.Label(heading, text="Lecture Capture", font=F_DISPLAY,
                                  bg=BG, fg=TEXT, anchor="w")
        self.l_heading.pack(anchor="w")
        self.l_subheading = tk.Label(heading, text="把课堂声音变成可检索、带时间的学习记录",
                                      font=F, bg=BG, fg=MUTED, anchor="w", justify="left")
        self.l_subheading.pack(anchor="w", pady=(1, 0))
        self.l_badge = tk.Label(header, text="准备中", font=F_BOLD, padx=12, pady=6,
                                bg=AMBER_SOFT, fg=AMBER)
        self.l_badge.pack(side="right", anchor="n", pady=4)

        # ---- 采集来源 ----
        mode_box = self._card(outer)
        mode_box.pack(fill="x", pady=(0, 12))
        tk.Label(mode_box, text="采集来源", font=F_TITLE, bg=CARD, fg=TEXT).pack(
            anchor="w", padx=18, pady=(14, 2))
        self.l_hint = tk.Label(mode_box, text="", fg=MUTED, bg=CARD, font=F_SMALL,
                               wraplength=680, justify="left", anchor="w")
        self.l_hint.pack(fill="x", padx=18)
        modes = tk.Frame(mode_box, bg=CARD)
        modes.pack(fill="x", padx=18, pady=(12, 16))
        modes.columnconfigure((0, 1), weight=1, uniform="mode")
        self.r_video = self._mode_button(
            modes, "在线视频", "跟随 Edge 视频播放位置", core.MODE_VIDEO, 0)
        self.r_classroom = self._mode_button(
            modes, "线下课堂", "麦克风收音，从开始计时", core.MODE_CLASSROOM, 1)

        # ---- 输出设置 ----
        box = self._card(outer)
        box.pack(fill="x", pady=(0, 12))
        tk.Label(box, text="保存设置", font=F_TITLE, bg=CARD, fg=TEXT).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(14, 10))
        self.l_name = tk.Label(box, text="文件名称", font=F_SMALL, bg=CARD, fg=MUTED)
        self.l_name.grid(
            row=1, column=0, sticky="w", padx=(18, 8))
        self.l_out = tk.Label(box, text="存放位置", font=F_SMALL, bg=CARD, fg=MUTED)
        self.l_out.grid(
            row=1, column=1, sticky="w", padx=(0, 8))
        self.e_name = self._entry(box, self.var_name)
        self.e_name.grid(row=2, column=0, sticky="ew", padx=(18, 10), pady=(4, 16), ipady=8)
        self.e_out = self._entry(box, self.var_out)
        self.e_out.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=(4, 16), ipady=8)
        self.b_browse = tk.Button(
            box, text="浏览", font=F_BOLD, command=self._browse, cursor="hand2",
            bg="#EEF2F7", fg=TEXT, activebackground="#E3E9F1", activeforeground=TEXT,
            relief="flat", bd=0, padx=16, pady=8, takefocus=True)
        self.b_browse.grid(row=2, column=2, padx=(0, 18), pady=(4, 16), sticky="ew")
        box.columnconfigure(0, weight=2)
        box.columnconfigure(1, weight=4)

        # ---- 实时状态 ----
        st = self._card(outer)
        st.pack(fill="both", expand=True, pady=(0, 12))
        tk.Label(st, text="实时状态", font=F_TITLE, bg=CARD, fg=TEXT).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(14, 10))
        self.l_cap = self._status_tile(st, "实时字幕", 1, 0)
        self.l_sess = self._status_tile(st, "时间来源", 1, 1)
        self.l_pos = self._status_tile(st, "当前时间", 1, 2)
        self.l_rows = self._status_tile(st, "已录入", 1, 3)

        transcript = self.transcript = tk.Frame(st, bg="#F7F9FC", highlightbackground=BORDER,
                              highlightthickness=1)
        transcript.grid(row=2, column=0, columnspan=4, sticky="nsew",
                        padx=18, pady=(10, 16))
        tk.Label(transcript, text="当前识别", font=F_SMALL, bg="#F7F9FC",
                 fg=MUTED).pack(anchor="w", padx=12, pady=(10, 4))
        self.l_cur = tk.Label(transcript, text="等待字幕输入…", font=F_MONO,
                              fg=TEXT, bg="#F7F9FC", wraplength=650,
                              justify="left", anchor="nw")
        self.l_cur.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        st.columnconfigure((0, 1, 2, 3), weight=1, uniform="status")
        st.rowconfigure(2, weight=1)

        # ---- 主要操作 ----
        btns = tk.Frame(controls, bg=BG)
        btns.pack(fill="x")
        btns.columnconfigure((0, 1), weight=1, uniform="action")
        self.b_start = tk.Button(
            btns, text="开始抓取", font=F_BIG, command=self._start, cursor="hand2",
            bg=BLUE, fg="white", activebackground=BLUE_HOVER, activeforeground="white",
            disabledforeground="#9CA3AF", relief="flat", bd=0, pady=12, takefocus=True)
        self.b_start.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.b_stop = tk.Button(
            btns, text="停止并保存", font=F_BIG, state="disabled", command=self._stop,
            cursor="hand2", bg="#E8ECF2", fg=TEXT, activebackground=RED_SOFT,
            activeforeground=RED, disabledforeground="#9CA3AF", relief="flat", bd=0,
            pady=12, takefocus=True)
        self.b_stop.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._bind_hover(self.b_start, BLUE, BLUE_HOVER)

        self.var_foot = tk.StringVar(value="正在检查 Windows 实时字幕与时间来源…")
        self.l_foot = tk.Label(controls, textvariable=self.var_foot, font=F_SMALL, fg=MUTED,
                               bg=BG, wraplength=720, justify="left", anchor="w")
        self.l_foot.pack(fill="x", pady=(10, 0))

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.canvas.bind("<Configure>", self._queue_layout)
        outer.bind("<Configure>", self._queue_layout)
        root.bind("<MouseWheel>", self._scroll_content)
        self._mode_changed(run_check=False)

    def _queue_layout(self, _event=None):
        if self.layout_job is None:
            self.layout_job = self.root.after_idle(self._layout_content)

    def _layout_content(self):
        self.layout_job = None
        width = max(1, self.canvas.winfo_width())
        compact = width < 620
        self.canvas.itemconfigure(self.content_window, width=width)
        if compact != self.compact:
            self.compact = compact
            self.l_heading.configure(font=("Segoe UI Variable Display", 18 if compact else 22, "bold"))
            self.l_badge.pack_forget()
            self.l_badge.pack(side="bottom" if compact else "right", anchor="w" if compact else "n", pady=4)
            for i, button in enumerate((self.r_video, self.r_classroom)):
                button.grid_configure(row=i if compact else 0, column=0 if compact else i,
                                      columnspan=2 if compact else 1,
                                      padx=(0, 0) if compact else ((0, 6) if i == 0 else (6, 0)),
                                      pady=(0, 6) if compact else 0)
            self.l_name.grid_configure(row=1, column=0, columnspan=3 if compact else 1)
            self.e_name.grid_configure(row=2, column=0, columnspan=3 if compact else 1,
                                       padx=(18, 18) if compact else (18, 10))
            self.l_out.grid_configure(row=3 if compact else 1, column=0 if compact else 1,
                                      columnspan=2 if compact else 1,
                                      padx=(18, 8) if compact else (0, 8))
            self.e_out.grid_configure(row=4 if compact else 2, column=0 if compact else 1,
                                      columnspan=2 if compact else 1,
                                      padx=(18, 8) if compact else (0, 8))
            self.b_browse.grid_configure(row=4 if compact else 2)
            for i, tile in enumerate(self.status_tiles):
                column = i % 2 if compact else i
                tile.grid_configure(row=1 + i // 2 if compact else 1, column=column,
                                     padx=(18 if column == 0 else 5,
                                           18 if column == (1 if compact else 3) else 5))
            for column in range(4):
                active = not compact or column < 2
                self.transcript.master.columnconfigure(column, weight=1 if active else 0,
                                                       uniform="status" if active else "")
            self.transcript.master.rowconfigure(2, weight=0 if compact else 1)
            self.transcript.master.rowconfigure(3, weight=1 if compact else 0)
            self.transcript.grid_configure(row=3 if compact else 2, columnspan=2 if compact else 4)
        self.l_subheading.configure(wraplength=max(150, width - (95 if compact else 190)))
        self.l_hint.configure(wraplength=max(100, width - 40))
        self.l_cur.configure(wraplength=max(100, width - 70))
        for label in (self.l_cap, self.l_sess, self.l_pos, self.l_rows):
            label.configure(wraplength=max(80, (width - 60) // (2 if compact else 4) - 24),
                            justify="left")
        self.l_foot.configure(wraplength=max(100, self.root.winfo_width() - 40))
        for button in (self.b_start, self.b_stop):
            button.configure(wraplength=max(120, (self.root.winfo_width() - 60) // 2))
        height = max(self.canvas.winfo_height(), self.content.winfo_reqheight())
        self.canvas.itemconfigure(self.content_window, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _scroll_content(self, event):
        if self.content.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"

    def _scroll_view(self, *args):
        self.canvas.yview(*args)

    def _card(self, parent):
        return tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)

    def _entry(self, parent, variable):
        return tk.Entry(parent, textvariable=variable, font=F, bg="#F8FAFC", fg=TEXT,
                        insertbackground=TEXT, relief="flat", bd=0,
                        highlightthickness=1, highlightbackground=BORDER,
                        highlightcolor=BLUE)

    def _mode_button(self, parent, title, subtitle, value, column):
        text = f"{title}\n{subtitle}"
        button = tk.Button(parent, text=text, font=F_BOLD, justify="left", anchor="w",
                           command=lambda: self._select_mode(value), cursor="hand2",
                           relief="flat", bd=0, padx=14, pady=10, takefocus=True)
        button.grid(row=0, column=column, sticky="ew", padx=(0, 6) if column == 0 else (6, 0))
        return button

    def _status_tile(self, parent, label, row, column):
        tile = tk.Frame(parent, bg="#F8FAFC", highlightbackground=BORDER,
                        highlightthickness=1)
        self.status_tiles.append(tile)
        left = 18 if column == 0 else 5
        right = 18 if column == 3 else 5
        tile.grid(row=row, column=column, sticky="ew", padx=(left, right), pady=(0, 8))
        tk.Label(tile, text=label, font=F_SMALL, bg="#F8FAFC", fg=MUTED).pack(
            anchor="w", padx=12, pady=(9, 2))
        lab = tk.Label(tile, text="检查中…", font=F_BOLD, bg="#F8FAFC", fg=GREY,
                       anchor="w")
        lab.pack(fill="x", padx=12, pady=(0, 9))
        return lab

    def _bind_hover(self, widget, normal, hover):
        widget.bind("<Enter>", lambda _e: widget.config(bg=hover)
                    if str(widget["state"]) == "normal" else None)
        widget.bind("<Leave>", lambda _e: widget.config(bg=normal)
                    if str(widget["state"]) == "normal" else None)

    def _select_mode(self, mode):
        self.var_mode.set(mode)
        self._mode_changed()

    def _refresh_mode_buttons(self):
        active = self.var_mode.get()
        for button, value in ((self.r_video, core.MODE_VIDEO),
                              (self.r_classroom, core.MODE_CLASSROOM)):
            selected = value == active
            button.config(bg=BLUE_SOFT if selected else "#F7F9FC",
                          fg=BLUE if selected else TEXT,
                          activebackground=BLUE_SOFT if selected else "#EEF2F7",
                          activeforeground=BLUE if selected else TEXT,
                          highlightthickness=1,
                          highlightbackground=BLUE if selected else BORDER,
                          highlightcolor=BLUE)

    def _set_status_badge(self, text, fg, bg):
        self.l_badge.config(text=text, fg=fg, bg=bg)

    def _mode_changed(self, run_check=True):
        self._refresh_mode_buttons()
        if self.var_mode.get() == core.MODE_CLASSROOM:
            self.l_hint.config(
                text="先按 Win+Ctrl+L，再在实时字幕中打开“设置 → 首选项 → 包括麦克风音频”。")
        else:
            self.l_hint.config(
                text="打开 Windows 实时字幕并在 Edge 播放课程；输出时间会跟随视频进度。")
        if run_check and not self.running:
            self._precheck()

    # ------------------------------------------------------------------ 预检
    def _boot_timeline(self):
        self.probe = core.CaptureEngine("_probe", core.default_out_dir(), self.var_app.get())
        self.probe.start_timeline()

    def _precheck(self):
        if self.running:
            return
        classroom = self.var_mode.get() == core.MODE_CLASSROOM
        if classroom:
            ok_sess = True
            self.l_sess.config(text="线下计时 · 无需浏览器", fg=GREEN)
            self.l_pos.config(text="新录从零 · 续录接上段", fg=GREY)
        else:
            snap = self.probe.session_snapshot()
            status = snap.get("status")
            ok_sess = status in ("playing", "paused", "stopped") and snap.get("position") is not None
            if ok_sess:
                self.l_sess.config(text=f"已连接 · {status} · Edge", fg=GREEN)
            else:
                self.l_sess.config(text="未找到 Edge 播放会话", fg=RED)

        alive = self.probe.caps.attach()
        if alive:
            self.l_cap.config(text="字幕已连接", fg=GREEN)
        else:
            self.l_cap.config(text="字幕未打开", fg=RED)

        if classroom and alive:
            self.var_foot.set("请确认实时辅助字幕已打开「包括麦克风音频」，然后点「开始抓取」。")
            self._set_status_badge("可以开始", GREEN, GREEN_SOFT)
        elif ok_sess and alive:
            self.var_foot.set("两个条件都就绪，可以点「开始抓取」。")
            self._set_status_badge("可以开始", GREEN, GREEN_SOFT)
        else:
            self.var_foot.set("请处理上方红色状态；准备好后切换一次采集来源即可重新检查。")
            self._set_status_badge("等待准备", AMBER, AMBER_SOFT)

    def _browse(self):
        cur = self.var_out.get().strip()
        init = cur if os.path.isdir(cur) else str(Path.home())
        d = filedialog.askdirectory(title="选择字幕存放位置", initialdir=init)
        if d:
            self.var_out.set(os.path.normpath(d))

    # ------------------------------------------------------------------ 开始
    def _refresh_start_label(self):
        if self.running:
            return
        name, out = self.var_name.get().strip(), self.var_out.get().strip()
        exists = bool(name and out) and any((Path(out) / f"{name}{suffix}").exists()
                                             for suffix in (".srt", ".md", ".raw.jsonl"))
        self.b_start.config(text="继续抓取 · 保留已有记录" if exists else "开始抓取")

    def _start(self):
        if self.running:
            return
        name = self.var_name.get().strip()
        out = self.var_out.get().strip()

        if not name:
            messagebox.showwarning("还差一步", "请先填写文件名称，例如 Lecture_01。")
            self.e_name.focus_set()
            return
        if not out:
            messagebox.showwarning("还差一步", "请先选择存放位置。")
            return
        if not os.path.isdir(out):
            if not messagebox.askyesno("目录不存在", f"这个目录还不存在：\n\n{out}\n\n要现在创建吗？"):
                return
            try:
                os.makedirs(out, exist_ok=True)
            except Exception as e:
                messagebox.showerror("创建失败", f"无法创建目录：\n{e}")
                return

        self._save_settings()

        mode = self.var_mode.get()
        eng = core.CaptureEngine(name, out, self.var_app.get(), mode=mode)
        eng.start_timeline()
        if mode == core.MODE_VIDEO:
            import time as _t
            _t.sleep(1.2)

        if not eng.attach_captions():
            messagebox.showerror("抓不到字幕",
                                 "没有找到「实时辅助字幕」窗口。\n\n"
                                 "请先按 Win+Ctrl+L 打开它，再点开始。")
            eng.stop_event.set()
            return

        try:
            eng.start()
        except Exception as e:
            eng.stop_event.set()
            messagebox.showerror("无法开始抓取", str(e))
            return
        self.engine = eng
        self.running = True
        self.saved_paths = None

        self._set_status_badge("正在录制", RED, RED_SOFT)
        self.b_start.config(state="disabled", text="正在抓取…", bg="#E8ECF2")
        self.b_stop.config(state="normal", bg=RED, fg="white",
                           activebackground=RED_HOVER, activeforeground="white")
        self._bind_hover(self.b_stop, RED, RED_HOVER)
        for w in (self.e_out, self.e_name, self.b_browse, self.r_video, self.r_classroom):
            w.config(state="disabled")
        if mode == core.MODE_CLASSROOM:
            self.var_foot.set(
                f"{'续录' if eng.resumed else '正在记录'}麦克风字幕：{os.path.join(out, name)}.*   —— 下课后点「停止并保存」。")
        else:
            self.var_foot.set(f"{'追加写入' if eng.resumed else '正在写入'}：{os.path.join(out, name)}.*   —— 看完课后点「停止并保存」。")

        self._tick()

    def _tick(self):
        if not self.running or self.engine is None:
            return
        try:
            st = self.engine.tick()
        except Exception as e:
            self._stop(reason=f"抓取异常：{e}")
            return

        snap = self.engine.session_snapshot()
        v = st.get("video")
        end = snap.get("end")
        pos_txt = "—"
        if v is not None:
            pos_txt = core.fmt_clock(v) + (f" / {core.fmt_clock(end)}" if end else "")
        self.l_pos.config(text=pos_txt, fg=TEXT)
        self.l_rows.config(text=f"{st.get('rows', 0)} 行", fg=GREEN if st.get("rows") else GREY)
        self.l_cur.config(text=(st.get("current") or "等待新的字幕内容…").strip()[:240])
        st_txt = snap.get("status")
        if self.engine.mode == core.MODE_CLASSROOM:
            self.l_sess.config(text="麦克风 · 线下计时", fg=GREEN)
        else:
            self.l_sess.config(text=f"Edge · {st_txt}",
                               fg=GREEN if st_txt in ("playing", "paused") else GREY)

        if st.get("ended"):
            self.var_foot.set("实时辅助字幕窗口已关闭 —— 正在保存已有内容…")
            self._stop()
            return

        if not st["captions_alive"]:
            self.l_cap.config(text="断开 · 自动重连中", fg=AMBER)
            self._set_status_badge("等待字幕重连", AMBER, AMBER_SOFT)
            self.var_foot.set("实时字幕暂时断开；记录保持打开，恢复字幕后自动继续。可点「停止并保存」。")
        else:
            self.l_cap.config(text="字幕已连接", fg=GREEN)
            self._set_status_badge("正在录制", RED, RED_SOFT)
            self.var_foot.set("正在追加记录，已有内容保留；结束时点「停止并保存」。")

        self.tick_job = self.root.after(300, self._tick)

    # ------------------------------------------------------------------ 停止
    def _stop(self, reason=None):
        if self.tick_job:
            try:
                self.root.after_cancel(self.tick_job)
            except Exception:
                pass
            self.tick_job = None
        if self.engine is None:
            return

        self._set_status_badge("正在保存", BLUE, BLUE_SOFT)
        self.b_stop.config(state="disabled", text="正在保存…", bg="#E8ECF2", fg=TEXT)
        self.root.update_idletasks()

        try:
            res = self.engine.stop()
        except Exception as e:
            messagebox.showerror("保存失败", f"写出文件时出错：\n{e}")
            res = None

        self.running = False
        self.engine = None
        self.b_start.config(state="normal", text="开始抓取", bg=BLUE, fg="white")
        self._refresh_start_label()
        self.b_stop.config(state="disabled", text="停止并保存", bg="#E8ECF2", fg=TEXT)
        for w in (self.e_out, self.e_name, self.b_browse, self.r_video, self.r_classroom):
            w.config(state="normal")
        self._refresh_mode_buttons()

        if res:
            srt, md, raw, n = res
            self.saved_paths = srt.parent
            self.l_rows.config(text=f"{n} 行（已保存）", fg=GREEN)
            self.l_cur.config(text="记录已保存。同名继续抓取会接着写；下一节课请换文件名称。")
            self._set_status_badge("保存完成", GREEN, GREEN_SOFT)
            self.var_foot.set(f"已保存 {n} 行 · {os.path.dirname(str(srt))}")
            if reason:
                self._set_status_badge("因错误停止", AMBER, AMBER_SOFT)
                self.var_foot.set(f"{reason}；已有记录已保存，可同名续录。")
            (messagebox.showwarning if reason else messagebox.showinfo)("因错误停止" if reason else "保存完成",
                                (f"{reason}\n\n" if reason else "") +
                                f"共 {n} 行。\n\n"
                                f"文件已保存到：\n{os.path.dirname(str(srt))}\n\n"
                                f"{os.path.basename(str(srt))}\n"
                                f"{os.path.basename(str(md))}")
        else:
            self.var_foot.set("没有产生文件（可能一行都没抓到）。")
            self._set_status_badge("未生成文件", AMBER, AMBER_SOFT)

    # ------------------------------------------------------------------ 关闭
    def _on_close(self):
        if self.running:
            if not messagebox.askyesno("还在抓取", "现在关闭会停止抓取并保存已有内容。要继续吗？"):
                return
            self._stop()
        try:
            self.probe.stop_event.set()
        except Exception:
            pass
        self._save_settings()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
