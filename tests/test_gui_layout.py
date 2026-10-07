import runpy
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import patch

App = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'LectureCapture.pyw'))['App']


class ResizableLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        with patch.object(App, '_load_settings', return_value={'name': 'layout-test', 'out': '.'}), \
                patch.object(App, '_boot_timeline'), patch.object(App, '_precheck'):
            self.app = App(self.root)
        # Tests inspect layout only, without caption polling or writing settings.
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.app.layout_job = None

    def resize(self, width, height):
        self.root.geometry(f'{width}x{height}')
        self.root.update()

    def assert_actions_visible(self):
        for button in (self.app.b_start, self.app.b_stop):
            self.assertTrue(button.winfo_ismapped())
            self.assertGreaterEqual(button.winfo_rooty(), self.root.winfo_rooty())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                 self.root.winfo_rooty() + self.root.winfo_height())

    def test_small_window_keeps_actions_and_scrolls_content(self):
        self.resize(460, 360)
        self.assertEqual((460, 360), (self.root.winfo_width(), self.root.winfo_height()))
        self.assertTrue(self.app.compact)
        for tile in self.app.status_tiles:
            self.assertGreater(tile.winfo_width(), 140)
        self.assert_actions_visible()
        self.assertGreater(self.app.content.winfo_reqheight(), self.app.canvas.winfo_height())
        self.app._scroll_view('moveto', 1)
        self.root.update()
        self.assertGreater(self.app.canvas.yview()[0], 0)
        self.assert_actions_visible()

    def test_repeated_resizing_restores_wide_and_compact_layout(self):
        for width, height, compact in [(780, 820, False), (520, 450, True),
                                        (1000, 600, False), (460, 360, True), (780, 820, False)]:
            self.resize(width, height)
            self.assertEqual(compact, self.app.compact)
            self.assert_actions_visible()
            self.assertEqual(3 if compact else 2, int(self.app.transcript.grid_info()['row']))
