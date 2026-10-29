"""Measured progress timing, resume and bounded console refresh."""

import io
import unittest
from unittest.mock import patch

from flex_photo.progress import Progress


class Clock:
    now = 0.

    def __call__(self):
        return self.now


class ProgressTests(unittest.TestCase):
    def test_resume_excludes_paused_time_and_reused_results(self):
        clock = Clock()
        progress = Progress(5, stream=io.StringIO(), clock=clock)
        clock.now = 10.
        progress.record_photo(10.)
        progress.close("paused")
        saved = progress.snapshot()
        clock.now = 10_000.
        resumed = Progress(saved["total"], evaluated=saved["evaluated"],
                           active_seconds=saved["active_seconds"],
                           processed_seconds=saved["processed_seconds"],
                           processed_count=saved["processed_count"],
                           stream=io.StringIO(), clock=clock)
        resumed.update(evaluated=3)  # Two reused results have no measured work.
        clock.now += 4.
        result = resumed.snapshot()
        self.assertEqual(result["active_seconds"], 14.)
        self.assertEqual(result["average_seconds"], 10.)
        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(result["eta_seconds"], 20.)
        self.assertEqual(result["percent"], 60.)
        resumed.record_photo(4.)
        self.assertEqual(resumed.snapshot()["average_seconds"], 7.)

    def test_eta_handles_missing_measurements_and_finalization(self):
        progress = Progress(2, stream=io.StringIO(), clock=Clock())
        self.assertIsNone(progress.snapshot()["eta_seconds"])
        progress.record_photo(3.)
        progress.update(finalization_remaining_seconds=4.)
        self.assertEqual(progress.snapshot()["eta_seconds"], 7.)
        progress.record_photo(5.)
        progress.update(stage="publication", status="completing")
        self.assertEqual(progress.snapshot()["eta_seconds"], 4.)
        progress.close("completed")
        self.assertEqual(progress.snapshot()["eta_seconds"], 0.)

    def test_redirected_output_is_periodic_and_meaningful(self):
        stream, clock = io.StringIO(), Clock()
        progress = Progress(100, stream=stream, clock=clock)
        for index in range(100):
            clock.now = index * .2
            progress.record_photo(.2)
        self.assertEqual(len(stream.getvalue().splitlines()), 1)
        clock.now = 31.
        progress.update(stage="publication", status="completing")
        progress.close("completed")
        output = stream.getvalue()
        self.assertEqual(len(output.splitlines()), 3)
        self.assertNotIn("\r", output)
        self.assertIn("completed | publication | 100/100 evaluated", output)
        self.assertIn("active 0:00:31", output)

    def test_tty_refresh_and_closed_stream_are_safe(self):
        stream, clock = io.StringIO(), Clock()
        stream.isatty = lambda: True
        with patch.dict("os.environ", {"TERM": "xterm"}):
            progress = Progress(3, stream=stream, clock=clock)
        progress.render()
        clock.now = 1.
        progress.update(status="pausing")
        progress.close("paused")
        self.assertEqual(stream.getvalue().count("\n"), 1)
        self.assertIn("\r", stream.getvalue())
        broken = io.StringIO()
        broken.close()
        Progress(stream=broken, clock=clock).close("incomplete")
        class BrokenPipe(io.StringIO):
            def write(self, _):
                raise BrokenPipeError
        Progress(stream=BrokenPipe(), clock=clock).close("incomplete")


if __name__ == "__main__":
    unittest.main()
