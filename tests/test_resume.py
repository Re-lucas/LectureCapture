import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture


class Captions:
    def __init__(self, text):
        self.frames = iter([[text], []])

    def alive(self):
        return True

    def read(self):
        return next(self.frames)


class ResumeTests(unittest.TestCase):
    def segment(self, folder, text, start=100, mode=capture.MODE_CLASSROOM, position=10):
        eng = capture.CaptureEngine("lesson", folder, mode=mode, settle=0.5)
        eng.caps = Captions(text)
        with patch("capture.time.monotonic", return_value=start):
            eng.start()
        for elapsed in (2, 3):
            with patch("capture.time.monotonic", return_value=start + elapsed), \
                 patch("capture.time.time", return_value=1_800_000_000 + elapsed):
                eng.tl.sample(position, capture.ST_PAUSED, 0, 900,
                              utc=1_800_000_000 + elapsed, last_updated=1_800_000_000 + elapsed)
                eng.tick()
        with patch("capture.time.monotonic", return_value=start + 4):
            result = eng.stop(split=False)
        return eng, result

    def test_restart_app_preserves_all_files_and_continues_time_and_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, first = self.segment(tmp, "First original explanation")
            originals = {path: path.read_bytes() for path in first[:3]}
            second, result = self.segment(tmp, "Second entirely different point", start=200)
            self.assertTrue(second.resumed)
            self.assertEqual(2, result[3])
            for path, original in originals.items():
                self.assertTrue(path.read_bytes().startswith(original), path.name)
            self.assertIn("2\n00:00:06,000 --> 00:00:07,000", result[0].read_text("utf-8"))
            self.assertIn("First original explanation", result[1].read_text("utf-8"))
            self.assertIn("Second entirely different point", result[1].read_text("utf-8"))
            self.assertEqual(8, json.loads(second.session_path.read_text())["elapsed"])

    def test_legacy_recording_without_metadata_can_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, result = self.segment(tmp, "Old legacy lesson")
            first.session_path.unlink()
            before = result[0].read_bytes()
            eng, resumed = self.segment(tmp, "Later newly recorded statement", start=400)
            self.assertEqual(4, eng.elapsed_offset)  # legacy Markdown duration
            self.assertEqual(2, resumed[3])
            self.assertTrue(resumed[0].read_bytes().startswith(before))

    def test_renamed_legacy_files_resume_without_rewriting_the_original_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng, result = self.segment(tmp, "Original historical words")
            eng.session_path.unlink()
            title = result[1].read_text("utf-8").replace("# lesson\n", "# Original lecture title\n", 1)
            result[1].write_text(title, encoding="utf-8")
            before = result[1].read_bytes()
            _, resumed = self.segment(tmp, "Further material after renaming", start=200)
            self.assertEqual(2, resumed[3])
            self.assertTrue(resumed[1].read_bytes().startswith(before))

    def test_video_resume_uses_actual_position_instead_of_classroom_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.segment(tmp, "Earlier video material", mode=capture.MODE_VIDEO, position=10)
            _, result = self.segment(tmp, "Newly resumed video material", mode=capture.MODE_VIDEO, position=500)
            self.assertIn("2\n00:08:20,000", result[0].read_text("utf-8"))
            self.assertIn("00:00:10,000", result[0].read_text("utf-8"))

    def test_empty_resume_keeps_srt_and_markdown_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = self.segment(tmp, "Keep this existing content")
            originals = {p: p.read_bytes() for p in result[:2]}
            eng = capture.CaptureEngine("lesson", tmp, mode=capture.MODE_CLASSROOM)
            eng.start()
            result = eng.stop()
            self.assertEqual(1, result[3])
            for path, original in originals.items():
                self.assertEqual(original, path.read_bytes())

    def test_different_mode_refuses_without_touching_recordings(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, result = self.segment(tmp, "Keep original mode")
            originals = {p: p.read_bytes() for p in result[:3]}
            other = capture.CaptureEngine("lesson", tmp, mode=capture.MODE_VIDEO)
            with self.assertRaisesRegex(ValueError, "采集方式不同"):
                other.start()
            for path, original in originals.items():
                self.assertEqual(original, path.read_bytes())
            self.assertIsNone(other.file_lock)

    def test_malformed_srt_refuses_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lesson.srt"
            path.write_bytes(b"important existing but malformed text")
            eng = capture.CaptureEngine("lesson", tmp, mode=capture.MODE_CLASSROOM)
            with self.assertRaisesRegex(ValueError, "字幕格式异常"):
                eng.start()
            self.assertEqual(b"important existing but malformed text", path.read_bytes())
            self.assertFalse((Path(tmp) / "lesson.raw.jsonl").exists())

    def test_raw_only_recording_refuses_instead_of_losing_unexported_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lesson.raw.jsonl"
            path.write_bytes(b'{"visible":["unexported old words"]}\n')
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "缺少字幕文件"):
                capture.CaptureEngine("lesson", tmp).start()
            self.assertEqual(before, path.read_bytes())

    def test_two_instances_cannot_write_same_lecture_and_lock_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = capture.CaptureEngine("lesson", tmp, mode=capture.MODE_CLASSROOM)
            second = capture.CaptureEngine("lesson", tmp, mode=capture.MODE_CLASSROOM)
            first.start()
            try:
                with self.assertRaisesRegex(RuntimeError, "另一个窗口"):
                    second.start()
            finally:
                first.stop()
            second.start()
            second.stop()

    def test_duplicate_start_does_not_truncate_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = capture.CaptureEngine("lesson", tmp, mode=capture.MODE_CLASSROOM)
            eng.start()
            before = eng.raw_path.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "重复开始"):
                eng.start()
            self.assertEqual(before, eng.raw_path.read_bytes())
            eng.stop()

    def test_external_edits_are_preserved_and_lock_released_on_save_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.segment(tmp, "Initial safely saved words")
            eng = capture.CaptureEngine("lesson", tmp, mode=capture.MODE_CLASSROOM)
            eng.start()
            with eng.md_path.open("a", encoding="utf-8") as f:
                f.write("User's independent edit")
            original = eng.md_path.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "其他程序修改"):
                eng.stop()
            self.assertEqual(original, eng.md_path.read_bytes())
            self.assertFalse(eng.started)
            self.assertIsNone(eng.file_lock)
            self.assertIsNone(eng.raw)

    def test_caption_window_disconnect_waits_and_reconnects_without_stopping(self):
        class ReconnectingCaptions:
            def __init__(self):
                self.connected = False
                self.attempts = 0
            def alive(self):
                return self.connected
            def attach(self, timeout=2):
                self.attempts += 1
                self.connected = self.attempts >= 2
                return self.connected
            def read(self):
                return ["Words after reconnection"]
        with tempfile.TemporaryDirectory() as tmp:
            eng = capture.CaptureEngine("lesson", tmp, mode=capture.MODE_CLASSROOM)
            eng.caps = ReconnectingCaptions()
            with patch("capture.time.monotonic", return_value=100):
                eng.start()
                missing = eng.tick()
            self.assertFalse(missing["captions_alive"])
            self.assertFalse(missing["ended"])
            self.assertTrue(eng.started)
            self.assertFalse(eng.raw.closed)
            with patch("capture.time.monotonic", return_value=103):
                restored = eng.tick()
            self.assertTrue(restored["captions_alive"])
            self.assertFalse(restored["ended"])
            with patch("capture.time.monotonic", return_value=104):
                result = eng.stop()
            self.assertIn("Words after reconnection", result[0].read_text("utf-8"))
            self.assertIn("captions_disconnected", result[2].read_text("utf-8"))
            self.assertIn("captions_reconnected", result[2].read_text("utf-8"))

    def test_same_engine_can_stop_and_resume_without_duplicating_previous_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng, _ = self.segment(tmp, "First stored paragraph")
            eng.caps = Captions("Second unrelated paragraph")
            eng.start()
            eng.tick()
            result = eng.stop(split=False)
            text = result[0].read_text("utf-8")
            self.assertEqual(1, text.count("First stored paragraph"))
            self.assertEqual(1, text.count("Second unrelated paragraph"))
            self.assertEqual(2, result[3])


if __name__ == "__main__":
    unittest.main()
