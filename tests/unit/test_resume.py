"""Recovery regressions with authored interpretations and real local effects."""

from dataclasses import replace
from datetime import timedelta
import errno
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import flex_photo.batch as batch
from flex_photo.interpretation import (FieldObservation, InterpretationAssets,
                                       InterpretationIssue, PhotoInterpretation)
from flex_photo.metadata import CaptureMetadata


class AbruptTermination(BaseException):
    """A process-loss boundary that ordinary exception handling cannot catch."""


class ResumeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="flex resume \u00e9 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source, self.destination, self.output = [self.root / part for part in ("source", "destination", "output")]
        self.source.mkdir()
        self.assets = InterpretationAssets(Path("engine"), Path("model"), "a" * 64)
        self.outcomes = {}
        self.originals = {}
        self.addCleanup(patch.stopall)
        patch.object(batch, "_validate_assets").start()
        self.interpret = patch.object(batch, "interpret_photo", side_effect=self._interpret).start()

    def _interpret(self, path, _):
        return self.outcomes[path.name]

    def photo(self, name):
        path = self.source / name
        self.originals[name] = ("authored original " + name).encode()
        path.write_bytes(self.originals[name])
        self.outcomes[name] = PhotoInterpretation(path, "trip_summary", (
            FieldObservation("trip_distance", "clear", raw_text="private requested reading",
                             value="0.0", unit="mi"),
            FieldObservation("trip_duration", "clear", value="00:12"),
            FieldObservation("trip_average_mpg", "absent"),
            FieldObservation("odometer", "absent")),
            CaptureMetadata("2031:06:12 12:00:00", "+00:00", None))
        return path

    def run_batch(self, **kwargs):
        return batch.process_batch(self.source, self.destination, self.output,
                                   assets=self.assets, **kwargs)

    def report(self, result):
        self.assertIsNotNone(result.report_path)
        return json.loads(result.report_path.read_bytes())

    def pause_after(self, name):
        event = threading.Event()
        def interpret(path, _):
            if path.name == name:
                event.set()
            return self.outcomes[path.name]
        self.interpret.side_effect = interpret
        result = self.run_batch(pause_event=event)
        self.assertEqual(result.status, "paused")
        self.interpret.side_effect = self._interpret
        self.interpret.reset_mock()
        return result

    def assert_one_trip(self):
        monthly = json.loads((self.output / "2031-06.json").read_bytes())
        self.assertEqual(len(monthly["trips"]), 1)
        self.assertEqual(monthly["trips"][0]["fields"]["trip_distance"], {"value": "0.0", "unit": "mi"})

    def test_pause_then_resume_does_not_repeat_verified_ocr(self):
        self.photo("a.heic")
        self.photo("b.heic")
        first = self.pause_after("a.heic")
        self.assertEqual(self.report(first)["progress"]["processed_count"], 1)
        journal = (self.output / ".flex-photo-checkpoint" / "results.jsonl").read_text()
        self.assertNotIn("private requested reading", journal)
        self.assertNotIn("raw_text", journal)
        self.assertEqual(len(list(self.source.glob("*.heic"))), 2)
        resumed = self.run_batch(resume=True)
        self.assertTrue(resumed.complete)
        self.assertEqual([call.args[0].name for call in self.interpret.call_args_list], ["b.heic"])
        self.assertEqual(self.report(resumed)["progress"]["processed_count"], 2)
        self.assert_one_trip()
        for name, original in self.originals.items():
            self.assertEqual((self.destination / name).read_bytes(), original)

    def test_failure_is_reused_and_reported_without_false_metadata_issue(self):
        failed = self.photo("a.heic")
        self.photo("b.heic")
        self.outcomes[failed.name] = PhotoInterpretation(failed, "unresolved", issues=(
            InterpretationIssue(failed, "individual OCR timeout", "preserve/report/continue"),))
        self.pause_after("a.heic")
        resumed = self.run_batch(resume=True)
        self.assertFalse(resumed.complete)
        self.assertEqual([call.args[0].name for call in self.interpret.call_args_list], ["b.heic"])
        issues = self.report(resumed)["issues"]
        self.assertEqual(sum(item["issue"] == "individual OCR timeout" for item in issues), 1)
        self.assertFalse(any("timestamp" in item["issue"] for item in issues if item["item"] == "a.heic"))
        self.assertEqual(failed.read_bytes(), self.originals[failed.name])
        self.assert_one_trip()

    def test_changed_input_invalidates_cache_and_preserves_previous_failure(self):
        changed = self.photo("a.heic")
        self.photo("b.heic")
        success = self.outcomes[changed.name]
        self.outcomes[changed.name] = PhotoInterpretation(changed, "unresolved", issues=(
            InterpretationIssue(changed, "original malformed image", "preserve/report/continue"),))
        self.pause_after(changed.name)
        changed.write_bytes(b"authored replacement input")
        self.outcomes[changed.name] = success
        resumed = self.run_batch(resume=True)
        self.assertTrue(resumed.complete)
        self.assertEqual([call.args[0].name for call in self.interpret.call_args_list], ["a.heic", "b.heic"])
        issues = self.report(resumed)["issues"]
        self.assertTrue(any("input changed" in item["issue"] for item in issues))
        self.assertTrue(any("previous input version" in item["issue"] and "original malformed image" in item["issue"]
                            for item in issues))
        self.assertEqual((self.destination / changed.name).read_bytes(), b"authored replacement input")

    def test_incompatible_config_stops_before_reuse_or_effects(self):
        self.photo("a.heic")
        self.photo("b.heic")
        self.pause_after("a.heic")
        result = self.run_batch(resume=True, window=timedelta(seconds=1))
        self.assertFalse(result.complete)
        self.interpret.assert_not_called()
        self.assertEqual(len(list(self.source.glob("*.heic"))), 2)
        self.assertFalse(list(self.destination.glob("*.heic")))
        self.assertTrue(any("configuration changed" in issue["issue"] for issue in self.report(result)["issues"]))
        self.assertTrue(self.run_batch(resume=True).complete)

    def test_unexpected_termination_restores_last_durable_result(self):
        self.photo("a.heic")
        self.photo("b.heic")
        def terminate(path, _):
            if path.name == "b.heic":
                raise AbruptTermination()
            return self.outcomes[path.name]
        self.interpret.side_effect = terminate
        with self.assertRaises(AbruptTermination):
            self.run_batch()
        self.interpret.side_effect = self._interpret
        self.interpret.reset_mock()
        result = self.run_batch(resume=True)
        self.assertTrue(result.complete)
        self.assertEqual([call.args[0].name for call in self.interpret.call_args_list], ["b.heic"])
        self.assert_one_trip()

    def test_repeated_pause_resume_and_postcompletion_resume_do_not_duplicate(self):
        for name in ("a.heic", "b.heic", "c.heic"):
            self.photo(name)
        self.pause_after("a.heic")
        event = threading.Event()
        def second_pause(path, _):
            event.set()
            return self.outcomes[path.name]
        self.interpret.side_effect = second_pause
        second = self.run_batch(resume=True, pause_event=event)
        self.assertEqual(second.status, "paused")
        self.assertEqual([call.args[0].name for call in self.interpret.call_args_list], ["b.heic"])
        self.interpret.side_effect = self._interpret
        self.interpret.reset_mock()
        last = self.run_batch(resume=True)
        self.assertTrue(last.complete)
        self.assertEqual([call.args[0].name for call in self.interpret.call_args_list], ["c.heic"])
        self.assertEqual(self.report(last)["progress"]["processed_count"], 3)
        before = (self.output / "2031-06.json").read_bytes()
        self.interpret.reset_mock()
        self.assertFalse(self.run_batch(resume=True).complete)
        self.interpret.assert_not_called()
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before)
        self.assert_one_trip()
        self.assertEqual(len(list(self.destination.glob("*.heic"))), 3)

    def test_pause_after_current_move_recovers_remaining_without_ocr(self):
        self.photo("a.heic")
        self.photo("b.heic")
        event = threading.Event()
        original_copy = batch._copy_file
        def pause_after_copy(source, temporary):
            original_copy(source, temporary)
            event.set()
        with patch.object(batch, "_copy_file", side_effect=pause_after_copy):
            result = self.run_batch(pause_event=event)
        self.assertEqual(result.status, "paused")
        self.assertTrue((self.destination / "a.heic").exists())
        self.assertTrue((self.source / "b.heic").exists())
        self.interpret.reset_mock()
        self.assertTrue(self.run_batch(resume=True).complete)
        self.interpret.assert_not_called()
        self.assert_one_trip()
        self.assertEqual(len(list(self.destination.glob("*.heic"))), 2)

    def test_month_published_before_state_commit_resumes_without_ocr_or_duplicate(self):
        self.photo("a.heic")
        original_write = batch._atomic_write
        def terminate_after_publication(path, data, expected):
            original_write(path, data, expected)
            if path.name == "2031-06.json":
                raise AbruptTermination()
        with patch.object(batch, "_atomic_write", side_effect=terminate_after_publication):
            with self.assertRaises(AbruptTermination):
                self.run_batch()
        before = (self.output / "2031-06.json").read_bytes()
        self.interpret.reset_mock()
        self.assertTrue(self.run_batch(resume=True).complete)
        self.interpret.assert_not_called()
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before)
        self.assert_one_trip()

    def test_failed_final_report_preserves_extractions_for_retry(self):
        self.photo("a.heic")
        self.photo("b.heic")
        original_write = batch._Report.write
        def fail_after_extraction(report):
            if self.interpret.call_count == 2:
                raise batch.BatchError("authored report failure after extraction")
            return original_write(report)
        with patch.object(batch._Report, "write", fail_after_extraction):
            self.assertFalse(self.run_batch().complete)
        self.assertTrue((self.output / ".flex-photo-checkpoint").exists())
        self.interpret.reset_mock()
        result = self.run_batch(resume=True)
        self.assertTrue(result.complete)
        self.interpret.assert_not_called()
        self.assert_one_trip()

    def test_pause_checkpoint_failure_reports_incomplete_and_retains_durable_result(self):
        self.photo("a.heic")
        self.photo("b.heic")
        event = threading.Event()
        def request_pause(path, _):
            event.set()
            return self.outcomes[path.name]
        self.interpret.side_effect = request_pause
        with patch.object(batch.Checkpoint, "save", side_effect=PermissionError(errno.EACCES, "authored denial")):
            result = self.run_batch(pause_event=event)
        self.assertFalse(result.complete)
        self.assertEqual(result.status, "incomplete")
        self.assertTrue(any("pause checkpoint save failed: PermissionError" in issue["issue"]
                            for issue in self.report(result)["issues"]))
        self.interpret.side_effect = self._interpret
        self.interpret.reset_mock()
        self.assertTrue(self.run_batch(resume=True).complete)
        self.assertEqual([call.args[0].name for call in self.interpret.call_args_list], ["b.heic"])

    def test_changed_source_during_ocr_finishes_evaluated_count_without_moving_it(self):
        original = self.photo("a.heic")
        def mutate(path, _):
            path.write_bytes(b"changed during OCR")
            return self.outcomes[path.name]
        self.interpret.side_effect = mutate
        result = self.run_batch()
        self.assertFalse(result.complete)
        progress = self.report(result)["progress"]
        self.assertEqual(progress["evaluated"], 1)
        self.assertEqual(progress["remaining"], 0)
        self.assertEqual(progress["percent"], 100.)
        self.assertEqual(original.read_bytes(), b"changed during OCR")
        self.assertFalse(list(self.destination.glob("*.heic")))

    def test_active_finalization_time_survives_restart_at_effect_boundary(self):
        self.photo("a.heic")
        self.photo("b.heic")
        clock = [0.]
        real_progress = batch.Progress
        def progress_factory(*args, **kwargs):
            return real_progress(*args, **kwargs, clock=lambda: clock[0])
        def interpreted(path, _):
            clock[0] += 2.
            return self.outcomes[path.name]
        self.interpret.side_effect = interpreted
        real_copy = batch._copy_file
        def terminate_second_move(source, temporary):
            if source.name == "b.heic":
                raise AbruptTermination()
            real_copy(source, temporary)
            clock[0] += 30.
        with patch.object(batch, "Progress", side_effect=progress_factory), \
                patch.object(batch.time, "monotonic", side_effect=lambda: clock[0]):
            with patch.object(batch, "_copy_file", side_effect=terminate_second_move):
                with self.assertRaises(AbruptTermination):
                    self.run_batch()
            manifest = json.loads((self.output / ".flex-photo-checkpoint" / "manifest.json").read_bytes())
            self.assertEqual(manifest["timing"]["active_seconds"], 34.)
            clock[0] = 1_000.  # Powered off/paused wall time must not become active work.
            self.interpret.reset_mock()
            result = self.run_batch(resume=True)
        self.assertTrue(result.complete)
        self.interpret.assert_not_called()
        self.assertEqual(self.report(result)["progress"]["active_seconds"], 34.)
        self.assert_one_trip()


class ReportReliabilityTests(unittest.TestCase):
    def test_inaccessible_report_hash_probe_cannot_escape_failure_handler(self):
        with tempfile.TemporaryDirectory(prefix="flex report ") as temporary:
            report = batch._Report(Path(temporary))
            report.issue("authored.heic", "new issue", "preserve")
            console = io.StringIO()
            with patch.object(batch, "_actual_hash", side_effect=PermissionError(errno.EACCES, "private path")), \
                    patch("sys.stderr", console):
                for _ in range(3):
                    with self.assertRaises(batch.BatchError):
                        report.write()
            self.assertFalse(report.saved)
            self.assertEqual(console.getvalue().count("report-failed:"), 1)
            self.assertIn("PermissionError", console.getvalue())
            self.assertNotIn("private path", console.getvalue())
            report.write()
            self.assertTrue(report.saved)

    def test_verified_publication_survives_temporary_cleanup_failure(self):
        with tempfile.TemporaryDirectory(prefix="flex report ") as temporary:
            report = batch._Report(Path(temporary))
            report.issue("authored.heic", "authored failure", "preserve", stage="interpretation")
            original_unlink = Path.unlink
            def blocked_unlink(path, *args, **kwargs):
                if path.name.startswith(".flex-write-"):
                    raise PermissionError(errno.EACCES, "authored cleanup denial")
                return original_unlink(path, *args, **kwargs)
            with patch.object(Path, "unlink", blocked_unlink), patch("sys.stderr", io.StringIO()):
                with self.assertRaises(batch.BatchError):
                    report.write()
            self.assertTrue(report.saved)
            self.assertEqual(report.expected, batch._hash_file(report.path))
            report.write()
            saved = json.loads(report.path.read_bytes())
            self.assertTrue(any(issue["stage"] == "report" for issue in saved["issues"]))
            self.assertTrue(report.saved)

    def test_error_summaries_preserve_items_without_repetitive_writes_or_console(self):
        with tempfile.TemporaryDirectory(prefix="flex report ") as temporary:
            real_write = batch._atomic_write
            with patch.object(batch, "_atomic_write", wraps=real_write) as writes:
                report = batch._Report(Path(temporary))
                for index in range(1000):
                    report.issue(str(index), "repeated failure", "preserve", stage="OCR")
                    report.issue(str(index), "repeated failure", "preserve", stage="OCR")
                self.assertEqual(writes.call_count, 1)
                report.write()
                self.assertEqual(writes.call_count, 2)
            saved = json.loads(report.path.read_bytes())
            self.assertEqual(len(saved["issues"]), 1000)
            self.assertEqual(saved["issue_summary"], [{"stage": "OCR", "issue": "repeated failure", "count": 1000}])
            report.issue("new", "new failure", "preserve")
            console = io.StringIO()
            with patch.object(batch, "_atomic_write", side_effect=PermissionError(errno.EACCES, "private path omitted")), \
                    patch("sys.stderr", console):
                for _ in range(3):
                    with self.assertRaises(batch.BatchError):
                        report.write()
            self.assertFalse(report.saved)
            self.assertEqual(console.getvalue().count("report-failed:"), 1)
            self.assertIn("PermissionError", console.getvalue())
            self.assertNotIn("private path omitted", console.getvalue())
            report.write()
            self.assertTrue(report.saved)


if __name__ == "__main__":
    unittest.main()
