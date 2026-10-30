"""Sparse monthly serialization and recoverable legacy index conversion."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import threading
from unittest.mock import patch

import flex_photo.batch as batch
from flex_photo.interpretation import FieldObservation, InterpretationAssets, InterpretationIssue, PhotoInterpretation, SharedAssetError
from flex_photo.metadata import CaptureMetadata
from flex_photo.capture_fallback import CAPTURE_POLICY


class InterruptedRewrite(BaseException):
    pass


class OutputUpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="flex sparse \u00e9 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "output"
        self.output.mkdir()

    def legacy(self):
        timestamp = "2031-06-12T12:00:00+00:00"
        fields = {"trip_distance": {"value": "0.0", "unit": "mi"},
                  "trip_duration": {"value": "00:00", "unit": None},
                  "trip_average_mpg": None, "odometer": None}
        entry = {"trip_date": "2031-06-12", "first_capture_times": [timestamp],
                 "last_capture_times": [timestamp], "month_assignment": "latest_capture_local", "fields": fields}
        monthly = {"schema_version": 1, "month": "2031-06", "trips": [entry]}
        encoded = batch._json_bytes(monthly)
        state = {"state_version": 1, "committed": [{"hashes": ["a" * 64], "captures": [timestamp],
                 "window_microseconds": 180_000_000, "month": "2031-06", "entry_index": 0,
                 "entry_digest": batch._hash_bytes(batch._json_bytes(entry))}],
                 "months": {"2031-06": batch._hash_bytes(encoded)}, "pending": None}
        (self.output / "2031-06.json").write_bytes(encoded)
        (self.output / batch._STATE).write_bytes(batch._json_bytes(state))
        return monthly, state

    def authored_batch(self, readings):
        source, destination = self.root / "source", self.root / "destination"
        source.mkdir()
        outcomes = {}
        for name, time, distance in readings:
            path = source / name
            path.write_bytes(("authored " + name).encode())
            outcomes[name] = PhotoInterpretation(path, "trip_summary", (
                FieldObservation("trip_distance", "clear", value=distance, unit="mi"),),
                CaptureMetadata("2031:06:12 " + time, "+00:00", None))
        return source, destination, outcomes, InterpretationAssets(Path("engine"), Path("model"), "a" * 64)

    def test_shared_asset_failure_after_interpretation_preserves_legacy_month_and_state(self):
        self.legacy()
        before_month = (self.output / "2031-06.json").read_bytes()
        before_state = (self.output / batch._STATE).read_bytes()
        source, destination, outcomes, assets = self.authored_batch([("new.heic", "12:20:00", "1.0")])
        with patch.object(batch, "_validate_assets", side_effect=[None, SharedAssetError("authored asset loss")]), \
                patch.object(batch, "interpret_photo", side_effect=lambda path, _: outcomes[path.name]):
            result = batch.process_batch(source, destination, self.output, assets=assets)
        self.assertFalse(result.complete)
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before_month)
        self.assertEqual((self.output / batch._STATE).read_bytes(), before_state)
        self.assertTrue((source / "new.heic").exists())
        self.assertFalse(list(destination.glob("*.heic")))
        self.assertFalse((self.output / batch._REWRITE).exists())

    def test_later_clear_conflict_preserves_legacy_month_and_state(self):
        self.legacy()
        before_month = (self.output / "2031-06.json").read_bytes()
        before_state = (self.output / batch._STATE).read_bytes()
        source, destination, outcomes, assets = self.authored_batch([
            ("first.heic", "12:20:00", "1.0"),
            ("second.heic", "12:40:00", "2.0"),
            ("third.heic", "12:40:00", "3.0")])
        with patch.object(batch, "_validate_assets"), \
                patch.object(batch, "interpret_photo", side_effect=lambda path, _: outcomes[path.name]):
            result = batch.process_batch(source, destination, self.output, assets=assets)
        self.assertFalse(result.complete)
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before_month)
        self.assertEqual((self.output / batch._STATE).read_bytes(), before_state)
        self.assertEqual(len(list(source.glob("*.heic"))), 3)
        self.assertFalse(list(destination.glob("*.heic")))
        self.assertFalse((self.output / batch._REWRITE).exists())

    def test_sparse_conversion_preserves_values_and_private_state_contract(self):
        before_month, before_state = self.legacy()
        summary = batch.rewrite_months(self.output)
        self.assertEqual(summary, {"rewritten_months": 1, "indexed_trips": 1})
        after = json.loads((self.output / "2031-06.json").read_bytes())
        self.assertEqual(after["schema_version"], 2)
        self.assertEqual(after["trips"][0]["fields"], {"trip_distance": {"value": "0.0", "unit": "mi"},
                                                      "trip_duration": {"value": "00:00"}})
        self.assertEqual({key: value for key, value in after["trips"][0].items() if key != "fields"},
                         {key: value for key, value in before_month["trips"][0].items() if key != "fields"})
        state, _, invalid = batch._load_state(self.output)
        self.assertEqual(invalid, set())
        expected = deepcopy(before_state)
        expected["months"]["2031-06"] = batch._hash_file(self.output / "2031-06.json")
        expected["committed"][0]["entry_digest"] = batch._hash_bytes(batch._json_bytes(after["trips"][0]))
        self.assertEqual(state, expected)
        self.assertIn(b'"pending": null', (self.output / batch._STATE).read_bytes())
        before = (self.output / "2031-06.json").read_bytes(), (self.output / batch._STATE).read_bytes()
        self.assertEqual(batch.rewrite_months(self.output)["rewritten_months"], 0)
        self.assertEqual(before, ((self.output / "2031-06.json").read_bytes(), (self.output / batch._STATE).read_bytes()))

    def test_all_missing_readings_remain_an_empty_fields_object(self):
        monthly, state = self.legacy()
        entry = monthly["trips"][0]
        entry["fields"] = dict.fromkeys(batch._FIELDS)
        encoded = batch._json_bytes(monthly)
        state["months"]["2031-06"] = batch._hash_bytes(encoded)
        state["committed"][0]["entry_digest"] = batch._hash_bytes(batch._json_bytes(entry))
        (self.output / "2031-06.json").write_bytes(encoded)
        (self.output / batch._STATE).write_bytes(batch._json_bytes(state))
        batch.rewrite_months(self.output)
        self.assertEqual(json.loads((self.output / "2031-06.json").read_bytes())["trips"][0]["fields"], {})

    def test_interruption_at_each_publication_boundary_resumes_once(self):
        real_write = batch._atomic_write
        for interrupted_name in (batch._REWRITE, "2031-06.json", batch._STATE):
            with self.subTest(boundary=interrupted_name):
                self.legacy()
                def interrupt(path, data, expected):
                    real_write(path, data, expected)
                    if path.name == interrupted_name:
                        raise InterruptedRewrite()
                with patch.object(batch, "_atomic_write", side_effect=interrupt), self.assertRaises(InterruptedRewrite):
                    batch.rewrite_months(self.output)
                self.assertTrue((self.output / batch._REWRITE).exists())
                batch.rewrite_months(self.output)
                state, _, invalid = batch._load_state(self.output)
                self.assertEqual(invalid, set())
                self.assertEqual(len(state["committed"]), 1)
                self.assertFalse((self.output / batch._REWRITE).exists())
                self.assertEqual(json.loads((self.output / "2031-06.json").read_bytes())["schema_version"], 2)

    def test_unreachable_or_edited_rewrite_files_are_preserved(self):
        self.legacy()
        real_write = batch._atomic_write
        def interrupt(path, data, expected):
            real_write(path, data, expected)
            if path.name == batch._REWRITE:
                raise InterruptedRewrite()
        with patch.object(batch, "_atomic_write", side_effect=interrupt), self.assertRaises(InterruptedRewrite):
            batch.rewrite_months(self.output)
        journal_path = self.output / batch._REWRITE
        journal = json.loads(journal_path.read_bytes())
        # State-after/month-before cannot result from the approved write order.
        (self.output / batch._STATE).write_text(journal["after_state"]["bytes"], encoding="utf-8")
        before = {p.name: p.read_bytes() for p in self.output.iterdir() if p.name != ".flex-photo.lock"}
        with self.assertRaisesRegex(batch.BatchError, "unreachable"):
            batch.rewrite_months(self.output)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir() if p.name != ".flex-photo.lock"})

    def test_forged_after_values_cannot_expand_rewrite_scope(self):
        self.legacy()
        real_write = batch._atomic_write
        def interrupt(path, data, expected):
            real_write(path, data, expected)
            if path.name == batch._REWRITE:
                raise InterruptedRewrite()
        with patch.object(batch, "_atomic_write", side_effect=interrupt), self.assertRaises(InterruptedRewrite):
            batch.rewrite_months(self.output)
        journal_path = self.output / batch._REWRITE
        journal = json.loads(journal_path.read_bytes())
        monthly = json.loads(journal["after_month"]["bytes"])
        monthly["trips"][0]["fields"]["trip_distance"]["value"] = "999"
        encoded = batch._json_bytes(monthly)
        journal["after_month"] = {"bytes": encoded.decode(), "hash": batch._hash_bytes(encoded)}
        journal_path.write_bytes(batch._json_bytes(journal))
        with self.assertRaisesRegex(batch.BatchError, "beyond sparse serialization"):
            batch.rewrite_months(self.output)

    def test_state_change_at_snapshot_read_cannot_be_adopted_or_published(self):
        _, state = self.legacy()
        state_path = self.output / batch._STATE
        month_path = self.output / "2031-06.json"
        before_month = month_path.read_bytes()
        before_state = state_path.read_bytes()
        expected = [batch._hash_bytes(before_state)]
        original_expected = list(expected)
        original_state = deepcopy(state)
        changed_state = before_state + b"\n "
        real_read = Path.read_bytes
        def change_at_read(path):
            if path == state_path:
                state_path.write_bytes(changed_state)
            return real_read(path)
        with batch._output_lock(self.output), patch.object(Path, "read_bytes", change_at_read), \
                patch.object(batch, "_atomic_write", wraps=batch._atomic_write) as publish:
            with self.assertRaisesRegex(batch.BatchError, "state changed while reading"):
                batch._rewrite_month(self.output, state, expected, "2031-06")
            publish.assert_not_called()
        self.assertEqual(month_path.read_bytes(), before_month)
        self.assertEqual(state_path.read_bytes(), changed_state)
        self.assertEqual(state, original_state)
        self.assertEqual(expected, original_expected)
        self.assertFalse((self.output / batch._REWRITE).exists())

    def test_legacy_pending_plan_publishes_original_schema_then_migrates_without_ocr(self):
        source, destination = self.root / "source", self.root / "destination"
        source.mkdir()
        original = source / "a.heic"
        original.write_bytes(b"authored photo")
        metadata = CaptureMetadata("2031:06:12 12:00:00", "+00:00", None)
        interpreted = PhotoInterpretation(original, "trip_summary", (
            FieldObservation("trip_duration", "clear", value="00:00"),), metadata)
        assets = InterpretationAssets(Path("engine"), Path("model"), "a" * 64)
        with patch.object(batch, "_validate_assets"), patch.object(batch, "interpret_photo", return_value=interpreted) as ocr:
            with patch.object(batch, "_copy_file", side_effect=OSError("authored copy stop")):
                self.assertFalse(batch.process_batch(source, destination, self.output, assets=assets).complete)
            state = json.loads((self.output / batch._STATE).read_bytes())
            entry = state["pending"]["trips"][0]["entry"]
            entry["fields"] = {field: entry["fields"].get(field) for field in batch._FIELDS}
            entry["fields"]["trip_duration"]["unit"] = None
            (self.output / batch._STATE).write_bytes(batch._json_bytes(state))
            schemas = []
            real_write = batch._atomic_write
            def observe(path, data, expected):
                if path.name == "2031-06.json":
                    schemas.append(json.loads(data)["schema_version"])
                return real_write(path, data, expected)
            ocr.reset_mock()
            with patch.object(batch, "_atomic_write", side_effect=observe):
                result = batch.process_batch(source, destination, self.output, assets=assets, resume=True)
            self.assertTrue(result.complete)
            ocr.assert_not_called()
        self.assertEqual(schemas, [1, 2])
        self.assertEqual((destination / original.name).read_bytes(), b"authored photo")
        self.assertEqual(len(json.loads((self.output / "2031-06.json").read_bytes())["trips"]), 1)


class BatchFallbackTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="flex fallback batch \u00e9 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source, self.destination, self.output = [self.root / name for name in ("source", "destination", "output")]
        self.source.mkdir()
        self.assets = InterpretationAssets(Path("engine"), Path("model"), "a" * 64)
        self.outcomes, self.births = {}, {}
        self.addCleanup(patch.stopall)
        patch.object(batch, "_validate_assets").start()
        self.ocr = patch.object(batch, "interpret_photo", side_effect=lambda path, _: self.outcomes[path.name]).start()
        patch.object(batch, "capture_inputs", side_effect=self.context).start()
        self.context_match = patch.object(batch, "capture_inputs_match", side_effect=lambda path, expected: self.context(path) == expected).start()

    def context(self, path):
        return {"creation_time_ns": self.births[path.name], "filename": path.name, "policy": CAPTURE_POLICY}

    def photo(self, name, *, birth=None):
        path = self.source / name
        path.write_bytes(("authored " + name).encode())
        self.births[name] = birth
        self.outcomes[name] = PhotoInterpretation(path, "trip_summary", (
            FieldObservation("trip_duration", "unclear"),), issues=(
                InterpretationIssue(path, "metadata reader unavailable", "preserve/report/exclude from grouping"),
                InterpretationIssue(path, "Trip Time unreadable", "report/retain earlier valid candidates")))
        return path

    def run_batch(self, **kwargs):
        return batch.process_batch(self.source, self.destination, self.output, assets=self.assets, **kwargs)

    def test_filename_grouping_uses_existing_first_to_last_window_and_filters_obsolete_metadata_issue(self):
        for name in ("20310612_120000123_iOS.heic", "20310612_120300123_iOS.heic", "20310612_120301123_iOS.heic"):
            self.photo(name)
        result = self.run_batch()
        self.assertTrue(result.complete)
        self.assertEqual(result.counts["moved"], 3)
        self.assertEqual(result.counts["trips"], 2)
        monthly = json.loads((self.output / "2031-06.json").read_bytes())
        first, second = monthly["trips"]
        self.assertEqual(first["first_capture_times"], ["2031-06-12T12:00:00.123-07:00"])
        self.assertEqual(first["last_capture_times"], ["2031-06-12T12:03:00.123-07:00"])
        self.assertEqual(second["first_capture_times"], ["2031-06-12T12:03:01.123-07:00"])
        self.assertEqual(first["fields"], {})
        issues = json.loads(result.report_path.read_bytes())["issues"]
        self.assertFalse(any(item["issue"] == "metadata reader unavailable" for item in issues))
        self.assertEqual(sum(item["issue"] == "Trip Time unreadable" for item in issues), 3)
        provenance = [item for item in issues if item["stage"] == "capture"]
        self.assertEqual(len(provenance), 3)
        self.assertTrue(all(item["issue"] == "capture time from filename" for item in provenance))
        self.assertTrue(all("America/Los_Angeles" in item["action"] for item in provenance))

    def test_bare_date_without_creation_time_skips_silently_even_with_field_issues(self):
        original = self.photo("20310612.heic")
        before = original.read_bytes()
        result = self.run_batch()
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(result.counts["skipped"], 1)
        self.assertEqual(original.read_bytes(), before)
        self.assertEqual(json.loads(result.report_path.read_bytes())["issues"], [])
        self.assertFalse(list(self.output.glob("????-??.json")))

    def test_changed_creation_time_revalidates_cached_capture_without_new_ocr(self):
        first = self.photo("a.heic", birth=1_939_525_200_000_000_000)
        self.photo("b.heic", birth=1_939_525_260_000_000_000)
        event = threading.Event()
        def pause(path, _):
            event.set()
            return self.outcomes[path.name]
        self.ocr.side_effect = pause
        self.assertEqual(self.run_batch(pause_event=event).status, "paused")
        self.births[first.name] += 30_000_000_000
        self.ocr.side_effect = lambda path, _: self.outcomes[path.name]
        self.ocr.reset_mock()
        result = self.run_batch(resume=True)
        self.assertTrue(result.complete)
        self.assertEqual([call.args[0].name for call in self.ocr.call_args_list], ["b.heic"])
        report = json.loads(result.report_path.read_bytes())
        self.assertEqual(report["progress"]["processed_count"], 2)
        self.assertTrue(any("file creation timestamp changed" in item["issue"] for item in report["issues"]))
        provenance = [item for item in report["issues"] if item["stage"] == "capture"]
        self.assertEqual({item["item"] for item in provenance}, {"a.heic", "b.heic"})
        self.assertTrue(all(item["issue"] == "capture time from file_creation" for item in provenance))

    def test_creation_time_change_after_copy_preserves_source_and_blocks_unsafe_recovery(self):
        original = self.photo("a.heic", birth=1_939_525_200_000_000_000)
        before = original.read_bytes()
        real_copy = batch._copy_file
        def mutate_after_copy(source, temporary):
            real_copy(source, temporary)
            self.births[source.name] += 60_000_000_000
        with patch.object(batch, "_copy_file", side_effect=mutate_after_copy):
            result = self.run_batch()
        self.assertFalse(result.complete)
        self.assertEqual(original.read_bytes(), before)
        self.assertEqual((self.destination / original.name).read_bytes(), before)
        self.ocr.reset_mock()
        resumed = self.run_batch(resume=True)
        self.assertFalse(resumed.complete)
        self.ocr.assert_not_called()
        self.assertEqual(original.read_bytes(), before)
        self.assertFalse(list(self.output.glob("????-??.json")))
        self.assertTrue(any("capture context changed" in issue["issue"] for issue in json.loads(resumed.report_path.read_bytes())["issues"]))

    def test_legacy_four_key_extraction_cache_upgrades_context_without_repeating_ocr(self):
        import hashlib
        self.photo("a.heic", birth=1_939_525_200_000_000_000)
        self.photo("b.heic", birth=1_939_525_260_000_000_000)
        event = threading.Event()
        def pause(path, _):
            event.set()
            return self.outcomes[path.name]
        self.ocr.side_effect = pause
        self.assertEqual(self.run_batch(pause_event=event).status, "paused")
        journal = self.output / ".flex-photo-checkpoint" / "results.jsonl"
        envelope = json.loads(journal.read_bytes())
        envelope["data"]["result"].pop("capture_inputs")
        encoded = json.dumps(envelope["data"], ensure_ascii=True, allow_nan=False, sort_keys=True,
                             separators=(",", ":")).encode()
        envelope["sha256"] = hashlib.sha256(encoded).hexdigest()
        journal.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
        self.ocr.side_effect = lambda path, _: self.outcomes[path.name]
        self.ocr.reset_mock()
        result = self.run_batch(resume=True)
        self.assertTrue(result.complete)
        self.assertEqual([call.args[0].name for call in self.ocr.call_args_list], ["b.heic"])
        self.assertEqual(json.loads(result.report_path.read_bytes())["progress"]["processed_count"], 2)

    def test_silent_date_only_skip_stays_incomplete_during_pending_effects_resume(self):
        bare = self.photo("20310612.heic")
        self.photo("20310612_120000123_iOS.heic")
        self.photo("20310612_120100123_iOS.heic")
        event = threading.Event()
        real_copy = batch._copy_file
        def pause_copy(source, temporary):
            real_copy(source, temporary)
            event.set()
        with patch.object(batch, "_copy_file", side_effect=pause_copy):
            self.assertEqual(self.run_batch(pause_event=event).status, "paused")
        self.ocr.reset_mock()
        result = self.run_batch(resume=True)
        self.assertFalse(result.complete)
        self.assertEqual(result.counts["skipped"], 1)
        self.ocr.assert_not_called()
        self.assertTrue(bare.exists())
        self.assertFalse(any(issue["item"] == bare.name for issue in json.loads(result.report_path.read_bytes())["issues"]))
        provenance = [item for item in json.loads(result.report_path.read_bytes())["issues"] if item["stage"] == "capture"]
        self.assertEqual(len(provenance), 2)
        self.assertTrue(all(item["issue"] == "capture time from filename" for item in provenance))

    def test_pending_capture_context_must_agree_with_resolved_capture_before_copy(self):
        original = self.photo("a.heic", birth=1_939_525_200_000_000_000)
        before = original.read_bytes()
        with patch.object(batch, "_copy_file", side_effect=OSError("authored stop before copy")):
            self.assertFalse(self.run_batch().complete)
        state_path = self.output / batch._STATE
        state = json.loads(state_path.read_bytes())
        context = state["pending"]["trips"][0]["files"][0]["capture_inputs"]
        context["creation_time_ns"] += 60_000_000_000
        self.births[original.name] = context["creation_time_ns"]
        state_path.write_bytes(batch._json_bytes(state))
        self.ocr.reset_mock()
        with patch.object(batch, "_copy_file", wraps=batch._copy_file) as copy:
            result = self.run_batch(resume=True)
            copy.assert_not_called()
        self.assertFalse(result.complete)
        self.ocr.assert_not_called()
        self.assertEqual(original.read_bytes(), before)
        self.assertFalse(list(self.destination.glob("*.heic")))
        self.assertFalse(list(self.output.glob("????-??.json")))
        self.assertTrue(any("private output state is invalid" in item["issue"]
                            for item in json.loads(result.report_path.read_bytes())["issues"]))

    def test_legacy_failure_without_context_is_reported_without_stat_or_new_fallback(self):
        from types import SimpleNamespace
        self.output.mkdir()
        report = batch._Report(self.output)
        path = self.photo("a.heic", birth=1_939_525_200_000_000_000)
        result = batch._compact_interpretation(self.outcomes[path.name])
        checkpoint = SimpleNamespace(results={path.name: {"result": result}})
        with patch.object(batch, "capture_inputs") as context:
            batch._replay_checkpoint_issues(checkpoint, report)
            context.assert_not_called()
        self.assertEqual(report.value["status"], "incomplete")
        self.assertFalse(any(item["stage"] == "capture" for item in report.value["issues"]))
        self.assertTrue(any("subsequent new run" in item["action"] for item in report.value["issues"]))


if __name__ == "__main__":
    unittest.main()
