import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture


class FakeCaptions:
    def __init__(self, frames):
        self.frames = iter(frames)

    def alive(self):
        return True

    def read(self):
        return next(self.frames)


class ClassroomModeTests(unittest.TestCase):
    def test_elapsed_clock_does_not_need_media_session(self):
        eng = capture.CaptureEngine("lesson", ".", mode=capture.MODE_CLASSROOM)
        eng.record_started = 100.0

        self.assertIsNone(eng.start_timeline())
        self.assertEqual(2.5, eng.capture_time(102.5))
        self.assertEqual("ready", eng.session_snapshot()["status"])

    def test_classroom_capture_writes_elapsed_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = capture.CaptureEngine(
                "lesson", tmp, settle=0.5, mode=capture.MODE_CLASSROOM)
            eng.caps = FakeCaptions([["Hello class"], []])

            with patch("capture.time.monotonic", return_value=100.0):
                eng.start()
            with patch("capture.time.monotonic", return_value=102.0):
                eng.tick()
            with patch("capture.time.monotonic", return_value=103.0):
                state = eng.tick()
            with patch("capture.time.monotonic", return_value=104.0):
                srt, md, raw, count = eng.stop()

            self.assertEqual(1, state["rows"])
            self.assertEqual(1, count)
            self.assertIn("00:00:02,000 --> 00:00:03,000", srt.read_text("utf-8"))
            self.assertIn("线下课堂（麦克风实时字幕）", md.read_text("utf-8"))
            self.assertIn('"mode": "classroom"', raw.read_text("utf-8"))

    def test_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            capture.CaptureEngine("lesson", ".", mode="unknown")


class VideoTimelineTests(unittest.TestCase):
    """SMTC 只在媒体事件时刷新 position，时间戳必须据此外推。

    浏览器整段播放都不刷新 position 时，旧实现拿
    采样时刻当基准，时间戳被反复钉回原处，在 1 秒附近来回跳。
    """

    T0 = 1_800_000_000.0
    END = 6654.5

    def setUp(self):
        self.tl = capture.Timeline("msedge")

    def feed(self, pos, utc, updated, status=capture.ST_PLAYING, rate=1.0):
        self.tl.sample(pos, status, rate, self.END, utc=utc, last_updated=updated)

    def test_frozen_position_still_advances(self):
        """播放中 position / last_updated 都停住时，时间仍要按时钟推进。"""
        t0 = self.T0
        self.feed(0.0, t0, t0)
        vals = []
        for i in range(1, 51):                 # 每 0.4 秒读一次，共 20 秒
            u = t0 + i * 0.4
            self.feed(0.0, u, t0)              # 浏览器没有上报任何新值
            vals.append(self.tl.video_time(u))
        self.assertTrue(all(b >= a for a, b in zip(vals, vals[1:])), vals)
        self.assertAlmostEqual(0.4, vals[0], places=6)
        self.assertAlmostEqual(20.0, vals[-1], places=6)

    def test_paused_returns_raw_position(self):
        t0 = self.T0
        self.feed(842.343, t0, t0, status=capture.ST_PAUSED, rate=0.0)
        self.assertAlmostEqual(842.343, self.tl.video_time(t0 + 30.0), places=3)

    def test_small_backward_jitter_is_clamped(self):
        t0 = self.T0
        self.feed(100.0, t0, t0)
        first = self.tl.video_time(t0 + 1.0)
        self.feed(99.4, t0 + 1.0, t0 + 1.0)    # position 回退 0.6 秒
        self.assertGreaterEqual(self.tl.video_time(t0 + 1.1), first)

    def test_seek_forward_is_followed(self):
        t0 = self.T0
        self.feed(100.0, t0, t0)
        self.tl.video_time(t0 + 0.1)
        self.feed(500.0, t0 + 0.5, t0 + 0.5)
        self.assertGreater(self.tl.video_time(t0 + 0.6), 500.0)

    def test_large_backward_seek_is_followed(self):
        t0 = self.T0
        self.feed(100.0, t0, t0)
        self.tl.video_time(t0 + 0.1)
        self.feed(500.0, t0 + 0.5, t0 + 0.5)
        self.tl.video_time(t0 + 0.6)
        self.feed(60.0, t0 + 1.0, t0 + 1.0)    # 用户把进度条拖回一分钟
        self.assertLess(self.tl.video_time(t0 + 1.1), 100.0)

    def test_resume_does_not_swallow_pause_duration(self):
        """恢复播放时 last_updated 还停在暂停前，不能把暂停时长算成进度。"""
        t0 = self.T0
        self.feed(100.0, t0, t0)
        self.tl.video_time(t0 + 1.0)
        self.feed(100.0, t0 + 2.0, t0 + 1.0,
                  status=capture.ST_PAUSED, rate=0.0)
        self.tl.video_time(t0 + 100.0)             # 暂停了 98 秒
        self.feed(100.0, t0 + 100.0, t0 + 1.0)     # 恢复播放，last_updated 仍未刷新
        resumed = self.tl.video_time(t0 + 100.5)
        self.assertGreaterEqual(resumed, 100.0)
        self.assertLess(resumed, 102.0)
        self.assertAlmostEqual(101.0, self.tl.video_time(t0 + 101.0), places=6)

    def test_missing_last_updated_still_advances(self):
        """拿不到 last_updated_time 时，降级路径也不能卡住。"""
        t0 = self.T0
        self.feed(5.0, t0, None)
        first = self.tl.video_time(t0 + 1.0)
        self.feed(5.0, t0 + 2.0, None)             # position 没变
        self.assertGreater(self.tl.video_time(t0 + 3.0), first)

    def test_backwards_query_does_not_reset_floor(self):
        t0 = self.T0
        self.feed(0.0, t0, t0)
        latest = self.tl.video_time(t0 + 30.0)
        self.tl.video_time(t0 + 5.0)               # 回溯查询
        self.assertGreaterEqual(self.tl.video_time(t0 + 31.0), latest)


class VideoEngineTests(unittest.TestCase):
    def test_rows_advance_while_smtc_position_is_frozen(self):
        t0 = 1_800_000_000.0
        with tempfile.TemporaryDirectory() as tmp:
            eng = capture.CaptureEngine("lesson", tmp, settle=0.5)
            eng.caps = FakeCaptions([["one"], ["one", "two"],
                                     ["one", "two"], []])
            clock = {"t": t0}
            eng.tl.sample(0.0, capture.ST_PLAYING, 1.0, 600.0,
                          utc=t0, last_updated=t0)
            with patch("capture.time.time", side_effect=lambda: clock["t"]), \
                 patch("capture.time.monotonic",
                       side_effect=lambda: clock["t"] - t0):
                eng.start()
                for step in range(4):
                    clock["t"] = t0 + step * 0.5
                    eng.tick()
                res = eng.stop(split=False)

            self.assertEqual(0.0, eng.committed[0]["t0"])
            self.assertAlmostEqual(1.5, eng.committed[0]["t1"], places=6)
            self.assertEqual(0.5, eng.committed[1]["t0"])
            srt = Path(res[0]).read_text("utf-8")
            self.assertIn("00:00:00,000 --> 00:00:01,500", srt)
            self.assertIn("00:00:00,500 --> 00:00:01,500", srt)


if __name__ == "__main__":
    unittest.main()
