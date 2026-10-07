#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lecture-capture 核心引擎
=========================
把 Windows 11 实时辅助字幕 (Live Captions) 的文字存下来。在线视频模式绑定
浏览器视频的【真实播放位置】，线下课堂模式使用【本次录制经过时间】。

- 字幕文字：Live Captions 窗口的 UI Automation 树（不是 OCR）
- 视频位置：系统媒体会话 SMTC（浏览器上报的 position）

本文件既可命令行运行，也作为 CaptureEngine 被 LectureCapture.pyw 的界面调用。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
import threading
import time
from difflib import SequenceMatcher
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import uiautomation as auto

WINDOW_CLASS = "LiveCaptionsDesktopWindow"
MODE_VIDEO = "video"
MODE_CLASSROOM = "classroom"
CAPTURE_MODES = (MODE_VIDEO, MODE_CLASSROOM)

# GlobalSystemMediaTransportControlsSessionPlaybackStatus
ST_CLOSED, ST_OPENED, ST_CHANGING, ST_STOPPED, ST_PLAYING, ST_PAUSED = range(6)
STATUS_NAMES = ["closed", "opened", "changing", "stopped", "playing", "paused"]

# 私有使用区：按钮里的图标字体，不是字幕
ICON_LO, ICON_HI = 0xE000, 0xF8FF
NOISE_MARKERS = (
    "已准备好", "正在收听", "实时辅助字幕", "字幕不可用",
    "Real-time caption", "Ready to", "Listening",
)


def is_icon(t):
    return bool(t) and all(ICON_LO <= ord(ch) <= ICON_HI for ch in t)


def is_noise(t):
    return (not t) or is_icon(t) or any(m in t for m in NOISE_MARKERS)


def fmt_srt(sec):
    if sec is None or sec < 0:
        sec = 0.0
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_clock(sec):
    if sec is None or sec < 0:
        sec = 0.0
    t = int(sec)
    return f"{t // 3600:d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def default_out_dir():
    """默认输出到「文档」；走 shell API，兼容 OneDrive 重定向。"""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)  # CSIDL_PERSONAL
        if buf.value:
            return buf.value
    except Exception:
        pass
    return str(Path.home() / "Documents")


# --------------------------------------------------------------------------
# 视频时间线
# --------------------------------------------------------------------------
# last_updated_time 相对本地钟允许的偏差：宽限未来 5 秒，最多陈旧 6 小时
CLOCK_FUTURE_TOL = 5.0
CLOCK_STALE_TOL = 6 * 3600.0
# 时间戳回退小于该幅度视为 SMTC 噪声，直接钳住（秒）
SEEK_BACK_TOL = 5.0


class Timeline:
    """把 SMTC 的媒体位置换算成单调推进的视频时间。

    SMTC 的 position 只在媒体事件（开始播放 / 暂停 / 拖动进度条）时刷新，
    播放过程中浏览器不会持续上报新值。因此外推基准必须是会话自报的
    last_updated_time（这个 position 的测量时刻），而不是我们各自的采样
    时刻——用采样时刻会在两次刷新之间把时间反复钉回原处，表现为时间线
    原地跳动、走不动。
    """

    def __init__(self, app_filter="msedge"):
        self.app_filter = (app_filter or "").lower()
        self.lock = threading.Lock()
        self.last = None          # (utc, pos, status, rate)
        self.anchor = None        # (position 的测量时刻 UTC, pos)
        self.end_seconds = None
        self.status_note = "starting"
        self.error = None
        self.mono = None          # 已输出的最大时间，用于单调钳制
        self.mono_at = None       # 更新 mono 时的查询时刻
        self.status_since = None  # 最近一次播放状态变化的时刻

    def sample(self, pos, status, rate, end, utc=None, last_updated=None):
        utc = time.time() if utc is None else utc
        with self.lock:
            prev = self.last
            if prev is None or prev[2] != status:
                self.status_since = utc
            self.last = (utc, pos, status, rate)
            self.anchor = (self._anchor_utc(pos, utc, last_updated), pos)
            if end and end > 0:
                self.end_seconds = end
            self.status_note = "ok"

    def _anchor_utc(self, pos, utc, last_updated):
        """这个 position 值是何时测得的（UTC 秒）。"""
        if last_updated is not None:
            age = utc - last_updated
            sane = -CLOCK_FUTURE_TOL <= age <= CLOCK_STALE_TOL
            if sane and self.status_since is not None:
                # 暂停期间 last_updated 不刷新；恢复播放时它可能还停在暂停前，
                # 拿它外推会把整段暂停时间算成播放进度。
                if last_updated < self.status_since - CLOCK_FUTURE_TOL:
                    sane = False
            if sane:
                return last_updated
        # 基准不可信：播放状态刚切换、或位置确实变了，都必须改以本次采样为准。
        # 否则沿用旧基准——播放中反复读到同一个 position 时，时间才能继续走。
        just_switched = (self.status_since is not None
                         and abs(self.status_since - utc) < 1e-6)
        if just_switched or self.anchor is None or pos != self.anchor[1]:
            return utc
        return self.anchor[0]

    def video_time(self, at_utc=None):
        with self.lock:
            s, anchor = self.last, self.anchor
        if s is None:
            return None
        utc, pos, status, rate = s
        at_utc = time.time() if at_utc is None else at_utc
        if status == ST_PLAYING:
            r = rate if rate and rate > 0 else 1.0
            base_utc, base_pos = anchor if anchor else (utc, pos)
            t = base_pos + (at_utc - base_utc) * r
        else:
            t = pos
        with self.lock:
            fresh = self.mono_at is None or at_utc >= self.mono_at
            if self.mono is not None and t < self.mono and (self.mono - t) <= SEEK_BACK_TOL:
                t = self.mono          # 抖动，不回退
            if fresh and (self.mono is None or t >= self.mono
                          or (self.mono - t) > SEEK_BACK_TOL):
                self.mono = t          # 正常前进，或用户真的拖了进度条
                self.mono_at = at_utc
        return t

    def snapshot(self):
        with self.lock:
            s, end, note, err, anchor = (self.last, self.end_seconds,
                                         self.status_note, self.error, self.anchor)
        if s is None:
            return {"status": note, "error": err, "end": end, "position": None}
        utc, pos, status, rate = s
        now = time.time()
        return {
            "status": STATUS_NAMES[status] if 0 <= status < 6 else str(status),
            "position": round(pos, 3),
            "rate": rate,
            "end": round(end, 3) if end else None,
            "age": round(now - utc, 2),
            "anchor_age": round(now - anchor[0], 2) if anchor else None,
            "error": err,
        }


def smtc_thread(tl, stop):
    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        )
    except Exception as e:
        tl.error = f"pywinrt import failed: {e}"
        return

    async def runner():
        mgr = await SessionManager.request_async()
        while not stop.is_set():
            try:
                chosen = None
                for s in mgr.get_sessions():
                    aid = (s.source_app_user_model_id or "").lower()
                    if tl.app_filter in aid:
                        chosen = s
                        break
                if chosen is None:
                    tl.status_note = "no-matching-session"
                else:
                    tlp = chosen.get_timeline_properties()
                    pb = chosen.get_playback_info()
                    updated = tlp.last_updated_time
                    tl.sample(
                        tlp.position.total_seconds(),
                        int(pb.playback_status),
                        float(pb.playback_rate or 0.0),
                        tlp.end_time.total_seconds(),
                        time.time(),
                        updated.timestamp() if updated is not None else None,
                    )
            except Exception as e:
                tl.error = f"{type(e).__name__}: {e}"
            await asyncio.sleep(0.4)

    try:
        asyncio.run(runner())
    except Exception as e:
        tl.error = f"smtc thread: {type(e).__name__}: {e}"


# --------------------------------------------------------------------------
# 字幕读取
# --------------------------------------------------------------------------
class Captions:
    def __init__(self):
        self.win = None

    def attach(self, timeout=2):
        w = auto.WindowControl(searchDepth=1, ClassName=WINDOW_CLASS)
        if not w.Exists(maxSearchSeconds=timeout):
            self.win = None
            return False
        self.win = w
        return True

    def alive(self):
        try:
            return self.win is not None and self.win.Exists(maxSearchSeconds=0.2)
        except Exception:
            return False

    def read(self):
        if self.win is None:
            return []
        blobs = []
        try:
            self._walk(self.win, blobs, 0)
        except Exception:
            return []
        lines = []
        for blob in blobs:
            # 实测：一个 TextBlock 的 Name 里会用换行聚合多行字幕
            for piece in (blob or "").splitlines():
                piece = piece.strip()
                if piece and not is_noise(piece):
                    lines.append(piece)
        return lines

    def _walk(self, ctrl, out, depth):
        if depth > 6:
            return
        try:
            children = ctrl.GetChildren()
        except Exception:
            return
        for c in children:
            try:
                ctype = c.ControlTypeName
            except Exception:
                continue
            if ctype == "TextControl":
                t = (c.Name or "").strip()
                if t and not is_icon(t):
                    out.append(t)
            elif ctype == "ButtonControl":
                continue          # 按钮内的图标字体不是字幕
            else:
                self._walk(c, out, depth + 1)


# --------------------------------------------------------------------------
# 合并 / 切分
# --------------------------------------------------------------------------
def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def is_growth(a, b):
    """Live Captions 逐词生长 + 原地修正：b 往往只是 a 的继续。

    判据：较短串有多大比例出现在较长串的开头。
    不用 ratio()，因为它会被两串长度差稀释。
    """
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    probe = long_[: max(len(short) + 5, 12)]
    m = SequenceMatcher(None, short.lower(), probe.lower())
    matched = sum(bl.size for bl in m.get_matching_blocks())
    return (matched / len(short)) >= 0.75


def merge_stutters(rows, threshold=0.78, gap=7.0):
    out = []
    for r in rows:
        if out:
            prev = out[-1]
            near = r["t0"] <= prev["t1"] + gap
            if near and (is_growth(prev["text"], r["text"])
                         or similar(prev["text"], r["text"]) >= threshold):
                if len(r["text"]) >= len(prev["text"]):
                    prev["text"] = r["text"]
                prev["t1"] = max(prev["t1"], r["t1"])
                continue
        out.append(dict(r))
    return out


SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
MIN_CUE = 0.8


def split_sentences(text):
    parts = [p.strip() for p in SENT_SPLIT.split((text or "").strip()) if p.strip()]
    return parts or [(text or "").strip()]


def split_rows(rows, min_cue=MIN_CUE):
    """按句子边界切开长段，时间戳按字符数比例分配。"""
    out = []
    for r in rows:
        sents = split_sentences(r["text"])
        if len(sents) <= 1:
            out.append(r)
            continue
        total = sum(len(s) for s in sents) or 1
        dur = max(r["t1"] - r["t0"], min_cue * len(sents))
        t = r["t0"]
        for s in sents:
            d = dur * (len(s) / total)
            out.append({"text": s, "t0": t, "t1": t + d,
                        "wall0": r["wall0"], "wall1": r["wall1"]})
            t += d
    return out


# --------------------------------------------------------------------------
# 引擎
# --------------------------------------------------------------------------
class CaptureEngine:
    """UI 无关的抓取引擎。调用方定期调用 tick()。"""

    def __init__(self, name, outdir, app_filter="msedge", settle=1.2,
                 mode=MODE_VIDEO):
        if mode not in CAPTURE_MODES:
            raise ValueError(f"unsupported capture mode: {mode}")
        self.name = name
        self.outdir = Path(outdir)
        self.mode = mode
        self.tl = Timeline(app_filter)
        self.caps = Captions()
        self.settle = settle
        self.stop_event = threading.Event()
        self.pending = {}
        self.committed = []
        self.raw = None
        self.raw_path = self.srt_path = self.md_path = None
        self.started = False
        self.last_lines = []
        self.last_flush = 0.0
        self.record_started = None
        self.elapsed_offset = 0.0
        self.previous_count = self.cue_index = 0
        self.resumed = False
        self.session_path = None
        self.file_lock = None
        self.last_attach_attempt = float("-inf")
        self.captions_missing = False
        self.previous_sizes = {}

    def attach_captions(self):
        return self.caps.attach()

    def start_timeline(self):
        if self.mode == MODE_CLASSROOM:
            return None
        t = threading.Thread(target=smtc_thread, args=(self.tl, self.stop_event), daemon=True)
        t.start()
        return t

    def session_snapshot(self):
        if self.mode == MODE_CLASSROOM:
            return {
                "status": "recording" if self.started else "ready",
                "position": self.capture_time(),
                "rate": 1.0,
                "end": None,
                "error": None,
            }
        return self.tl.snapshot()

    def capture_time(self, at=None):
        """返回当前输出时间戳：视频位置（UTC 时基），或线下录制经过时间（单调时基）。"""
        if self.mode == MODE_CLASSROOM:
            if self.record_started is None:
                return 0.0
            at = time.monotonic() if at is None else at
            return self.elapsed_offset + max(0.0, at - self.record_started)
        return self.tl.video_time(time.time() if at is None else at)

    def start(self):
        if self.started:
            raise RuntimeError("已经在抓取，不能重复开始。")
        if not self.name or Path(self.name).name != self.name or self.name in (".", ".."):
            raise ValueError("文件名称不能包含目录路径。")
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.raw_path = self.outdir / f"{self.name}.raw.jsonl"
        self.srt_path = self.outdir / f"{self.name}.srt"
        self.md_path = self.outdir / f"{self.name}.md"
        self.session_path = self.outdir / f"{self.name}.session.json"
        self._acquire_lock()
        try:
            self._load_previous()
            self.pending.clear()
            self.committed.clear()
            self.last_lines = []
            self.stop_event.clear()
            self.raw = self.raw_path.open("a", encoding="utf-8")
            if self.raw_path.stat().st_size:
                with self.raw_path.open("rb") as old:
                    old.seek(-1, 2)
                    if old.read(1) != b"\n":
                        self.raw.write("\n")
            self.raw.write(json.dumps({"event": "session_start", "mode": self.mode,
                                       "previous_rows": self.previous_count,
                                       "elapsed_offset": self.elapsed_offset}) + "\n")
            self.raw.flush()
        except Exception:
            if self.raw:
                self.raw.close()
                self.raw = None
            self._release_lock()
            raise
        self.record_started = time.monotonic()
        self.started = True

    def _acquire_lock(self):
        """Prevent two app instances from appending the same lecture concurrently."""
        import msvcrt
        handle = (self.outdir / f".{self.name}.capture.lock").open("a+b")
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            handle.close()
            raise RuntimeError("另一个窗口正在抓取这个文件，请先停止那个窗口。") from exc
        self.file_lock = handle

    def _release_lock(self):
        if self.file_lock:
            import msvcrt
            try:
                self.file_lock.seek(0)
                msvcrt.locking(self.file_lock.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                self.file_lock.close()
                self.file_lock = None

    def _load_previous(self):
        paths = (self.srt_path, self.md_path, self.raw_path, self.session_path)
        for path in paths:
            if path.exists() and not path.is_file():
                raise ValueError(f"输出路径不是文件：{path.name}")
        self.resumed = any(p.exists() and p.stat().st_size for p in paths)
        self.previous_count = self.cue_index = 0
        self.elapsed_offset = 0.0
        old_md = self.md_path.read_text("utf-8-sig") if self.md_path.exists() else ""
        meta = json.loads(self.session_path.read_text("utf-8")) if self.session_path.exists() else {}
        old_mode = meta.get("mode")
        if not old_mode and "- 记录方式: 线下课堂" in old_md:
            old_mode = MODE_CLASSROOM
        elif not old_mode and "- 记录方式: 在线视频" in old_md:
            old_mode = MODE_VIDEO
        if not old_mode and "- 视频总长:" in old_md:
            old_mode = MODE_VIDEO
        elif not old_mode and "- 录制时长:" in old_md:
            old_mode = MODE_CLASSROOM
        if old_mode and old_mode != self.mode:
            raise ValueError("同名记录的采集方式不同，请使用原采集方式续录，或换一个文件名称。")
        if old_md and not (re.match(r"^# [^\n]+\n", old_md) and old_mode in CAPTURE_MODES):
            raise ValueError("已有文字稿格式无法确认，旧文件未改动；请换一个文件名称。")
        if not self.srt_path.exists() and any(p.exists() and p.stat().st_size for p in (self.raw_path, self.md_path)):
            raise ValueError("已有记录缺少字幕文件，不能安全续录。旧文件未改动，请先恢复记录或换一个名称。")
        if self.srt_path.exists():
            text = self.srt_path.read_text("utf-8-sig").strip()
            cue = re.compile(r"^(\d+)\n(\d{2,}:\d{2}:\d{2},\d{3}) --> (\d{2,}:\d{2}:\d{2},\d{3})\n(.+)$", re.S)
            for block in re.split(r"\n\s*\n", text) if text else []:
                match = cue.fullmatch(block)
                if not match or int(match[1]) <= self.cue_index:
                    raise ValueError("已有字幕格式异常，旧文件未改动；请修复字幕或换一个名称。")
                self.cue_index = int(match[1])
                self.previous_count += 1
                h, m, s, ms = map(int, re.split(r"[:,]", match[3]))
                if m >= 60 or s >= 60:
                    raise ValueError("已有字幕时间格式异常，旧文件未改动。")
                self.elapsed_offset = max(self.elapsed_offset, h * 3600 + m * 60 + s + ms / 1000)
        elapsed = meta.get("elapsed", 0)
        if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("续录时间记录异常，旧文件未改动。")
        self.elapsed_offset = max(self.elapsed_offset, elapsed)
        if not meta:
            for h, m, s in re.findall(r"- 录制时长: (\d+):(\d{2}):(\d{2})", old_md):
                self.elapsed_offset = max(self.elapsed_offset, int(h) * 3600 + int(m) * 60 + int(s))
        self.previous_sizes = {p: p.stat().st_size if p.exists() else 0 for p in (self.srt_path, self.md_path)}

    def tick(self):
        """执行一次采集，返回状态字典。"""
        now = time.monotonic()
        state = {
            "captions_alive": self.caps.alive(),
            "rows": self.previous_count + len(self.committed),
            "current": self.last_lines[-1] if self.last_lines else "",
            "video": self.capture_time(),
            "ended": False,
        }
        if not state["captions_alive"]:
            if now - self.last_attach_attempt >= 2:
                self.last_attach_attempt = now
                state["captions_alive"] = self.caps.attach(timeout=0.1)
            if not state["captions_alive"]:
                if not self.captions_missing:
                    self._flush_pending()
                    self.captions_missing = True
                    if self.raw:
                        self.raw.write(json.dumps({"event": "captions_disconnected", "wall": now}) + "\n")
                        self.raw.flush()
                state["rows"] = self.previous_count + len(self.committed)
                return state
        if self.captions_missing:
            self.captions_missing = False
            if self.raw:
                self.raw.write(json.dumps({"event": "captions_reconnected", "wall": now}) + "\n")

        lines = self.caps.read()
        self.last_lines = lines
        seen = set()
        for t in lines:
            if t in self.pending:
                self.pending[t][1] = now
            else:
                self.pending[t] = [now, now, self.capture_time()]
            seen.add(t)

        for t in list(self.pending.keys()):
            first, last, vstart = self.pending[t]
            if t not in seen and (now - last) >= self.settle:
                vend = self.capture_time()
                self.committed.append({
                    "text": t,
                    "t0": vstart if vstart is not None else 0.0,
                    "t1": vend if vend is not None else (vstart or 0.0) + 2.0,
                    "wall0": first, "wall1": last,
                })
                del self.pending[t]

        state["rows"] = self.previous_count + len(self.committed)
        state["current"] = lines[-1] if lines else ""
        state["video"] = self.capture_time()

        if self.raw:
            self.raw.write(json.dumps({
                "wall": round(now, 3),
                "mode": self.mode,
                "video": None if state["video"] is None else round(state["video"], 3),
                "media": self.tl.snapshot() if self.mode == MODE_VIDEO else None,
                "visible": lines,
                "committed": len(self.committed),
            }, ensure_ascii=False) + "\n")
            if now - self.last_flush > 2.0:
                self.raw.flush()
                self.last_flush = now
        return state

    def _flush_pending(self):
        for t, (first, last, vstart) in self.pending.items():
            vend = self.capture_time()
            self.committed.append({
                "text": t,
                "t0": vstart if vstart is not None else 0.0,
                "t1": vend if vend is not None else (vstart or 0.0) + 2.0,
                "wall0": first, "wall1": last,
            })
        self.pending.clear()

    def stop(self, split=True):
        """收尾并写出文件，返回 (srt, md, raw, row_count)。"""
        if not self.started:
            return None
        try:
            return self._save_segment(split)
        finally:
            if self.raw:
                self.raw.close()
                self.raw = None
            self.started = False
            self.stop_event.set()
            self._release_lock()

    def _save_segment(self, split):
        self._flush_pending()
        self.stop_event.set()

        self.committed.sort(key=lambda r: (r["t0"], r["wall0"]))
        rows = merge_stutters(self.committed)
        if split:
            rows = split_rows(rows)
        for r in rows:
            if r["t1"] <= r["t0"]:
                r["t1"] = r["t0"] + 1.0

        for path, size in self.previous_sizes.items():
            if (path.stat().st_size if path.exists() else 0) != size:
                raise RuntimeError("抓取期间输出文件被其他程序修改，已保留原文件和原始采样。")
        with self.srt_path.open("a", encoding="utf-8") as f:
            if rows and self.previous_sizes[self.srt_path]:
                f.write("\n\n")
            for i, r in enumerate(rows, self.cue_index + 1):
                f.write(f"{i}\n{fmt_srt(r['t0'])} --> {fmt_srt(r['t1'])}\n{r['text']}\n\n")

        end = (self.capture_time() if self.mode == MODE_CLASSROOM
               else self.tl.end_seconds)
        total = self.previous_count + len(rows)
        with self.md_path.open("a", encoding="utf-8") as f:
            if not self.previous_sizes[self.md_path]:
                f.write(f"# {self.name}\n\n")
                if self.mode == MODE_CLASSROOM:
                    f.write("- 记录方式: 线下课堂（麦克风实时字幕）\n")
                    f.write(f"- 录制时长: {fmt_clock(end)}\n")
                else:
                    f.write("- 记录方式: 在线视频\n")
                    f.write(f"- 视频总长: {fmt_clock(end) if end else '未知'}\n")
                f.write(f"- 定稿行数: {total}\n\n")
            elif rows:
                f.write(f"\n\n## 续录 · 本段 {len(rows)} 行，累计 {total} 行\n\n")
                if self.mode == MODE_CLASSROOM:
                    f.write(f"- 录制时长: {fmt_clock(end)}\n\n")
            for r in rows:
                f.write(f"**[{fmt_clock(r['t0'])}]** {r['text']}\n\n")

        elapsed = max([self.capture_time() or 0] + [r["t1"] for r in rows]) if self.mode == MODE_CLASSROOM else 0
        temp = self.session_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps({"version": 1, "mode": self.mode, "elapsed": elapsed,
                                    "rows": total}, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.session_path)
        if self.raw:
            self.raw.write(json.dumps({"event": "session_stop", "mode": self.mode,
                                       "rows": total, "elapsed": elapsed}) + "\n")
            self.raw.flush()
        return self.srt_path, self.md_path, self.raw_path, total


# --------------------------------------------------------------------------
# 命令行入口
# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Capture Windows Live Captions")
    ap.add_argument("--name", required=True, help="输出文件名，例如 Lecture_01")
    ap.add_argument("--out", default=default_out_dir(), help="输出目录，默认「文档」")
    ap.add_argument("--app", default="msedge", help="媒体会话过滤，默认 msedge")
    ap.add_argument("--mode", choices=CAPTURE_MODES, default=MODE_VIDEO,
                    help="video=在线视频时间轴；classroom=线下课堂经过时间")
    ap.add_argument("--settle", type=float, default=1.2, help="一行停止变化多久后算定稿(秒)")
    ap.add_argument("--poll", type=float, default=0.3, help="读取字幕间隔(秒)")
    ap.add_argument("--no-split", action="store_true", help="不按句子切分")
    ap.add_argument("--list-sessions", action="store_true", help="只列出当前媒体会话后退出")
    args = ap.parse_args(argv)

    eng = CaptureEngine(args.name, args.out, args.app, args.settle, args.mode)
    eng.start_timeline()

    if args.list_sessions:
        time.sleep(2.0)
        eng.stop_event.set()
        print(json.dumps(eng.session_snapshot(), ensure_ascii=False, indent=2))
        return 0

    time.sleep(1.0)
    snap = eng.session_snapshot()
    if args.mode == MODE_CLASSROOM:
        print("[i] 线下课堂模式：时间戳从开始抓取起计算，不需要浏览器媒体会话。")
        print("[i] 请在实时辅助字幕中打开：设置 → 首选项 → 包括麦克风音频。")
    else:
        print(f"[i] 媒体会话: {snap}")
        if snap.get("end"):
            print(f"[i] 视频总长: {fmt_clock(snap['end'])}")

    if not eng.attach_captions():
        print("[!] 没有找到 Live Captions 窗口。请先按 Win+Ctrl+L 打开实时辅助字幕，再重跑。")
        eng.stop_event.set()
        return 2
    print("[i] 已连接 Live Captions。Ctrl+C 结束并生成字幕文件。")

    eng.start()
    try:
        while True:
            st = eng.tick()
            if st.get("ended"):
                print("\n[!] Live Captions 窗口消失了，正在收尾。")
                break
            if not st["captions_alive"]:
                print("  ... 实时字幕暂时断开，等待自动重连；Ctrl+C可停止并保存。", end="\r")
                time.sleep(args.poll)
                continue
            v = st["video"]
            print(f"  ... 视频 {fmt_clock(v) if v is not None else '--:--:--'} | "
                  f"已定稿 {st['rows']} 行 | 会话 {eng.session_snapshot().get('status')}", end="\r")
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\n[i] 收到 Ctrl+C，收尾中...")

    res = eng.stop(split=not args.no_split)
    if res:
        srt, md, raw, n = res
        print(f"\n[✓] 完成：{n} 行")
        print(f"    {srt}")
        print(f"    {md}")
        print(f"    {raw}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
