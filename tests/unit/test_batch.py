"""Approved batch outcomes with authored observations, not OCR accuracy claims."""

from datetime import datetime, timedelta, timezone
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import flex_photo.batch as batch
from flex_photo.interpretation import (
    FieldObservation, InterpretationAssets, InterpretationIssue, PhotoInterpretation, SharedAssetError,
)
from flex_photo.metadata import CaptureMetadata


class BatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="flex batch \u00e9 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.destination = self.root / "destination"
        self.output = self.root / "output"
        self.source.mkdir()
        self.assets = InterpretationAssets(Path("engine"), Path("models"), "0" * 64)
        self.outcomes = {}
        self.saved = {}
        self.addCleanup(patch.stopall)
        patch.object(batch, "_validate_assets").start()
        self.interpret = patch.object(batch, "interpret_photo", side_effect=self._interpret).start()

    def _interpret(self, path, assets):
        return self.outcomes[path.name]

    def photo(self, name, capture, fields=None, *, layout="trip_summary", payload=None):
        path = self.source / name
        data = payload if payload is not None else ("authored fixture " + name).encode()
        path.write_bytes(data)
        self.saved[name] = data
        values = fields or {}
        observations = tuple(
            FieldObservation(key, "clear", value=value[0], unit=value[1])
            if (value := values.get(key)) is not None else FieldObservation(key, "absent")
            for key in ("trip_distance", "trip_duration", "trip_average_mpg", "odometer")
        )
        original = capture.strftime("%Y:%m:%d %H:%M:%S")
        offset = capture.strftime("%z")
        offset = offset[:3] + ":" + offset[3:]
        metadata = CaptureMetadata(original, offset, None)
        self.outcomes[name] = PhotoInterpretation(path, layout, observations, metadata)
        return path

    def run_batch(self, *, window=timedelta(minutes=3)):
        return batch.process_batch(self.source, self.destination, self.output,
                                   assets=self.assets, window=window)

    def month(self, month="2031-06"):
        return json.loads((self.output / (month + ".json")).read_text(encoding="utf-8"))

    def assert_sources_preserved(self, names):
        for name in names:
            self.assertEqual((self.source / name).read_bytes(), self.saved[name])

    def test_independent_latest_clear_zero_and_earlier_valid_duration(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("first.heic", start, {"trip_duration": ("02:16", None),
                                        "trip_average_mpg": ("41.20", "MPG")})
        self.photo("last.heic", start + timedelta(minutes=2), {"trip_distance": ("0.0", "mi")})
        latest = self.outcomes["last.heic"]
        self.outcomes["last.heic"] = replace(latest, observations=tuple(
            FieldObservation("trip_duration", "unclear", raw_text="Trip Time 02:70")
            if item.field_id == "trip_duration" else item for item in latest.observations),
            issues=(InterpretationIssue(latest.path, "Trip Time malformed",
                                        "report/retain earlier valid candidates"),))
        result = self.run_batch()
        self.assertTrue(result.complete)
        document = self.month()
        self.assertEqual(set(document), {"schema_version", "month", "trips"})
        trip, = document["trips"]
        self.assertEqual(set(trip), {"trip_date", "first_capture_times", "last_capture_times",
                                     "month_assignment", "fields"})
        self.assertEqual(trip["fields"], {
            "trip_distance": {"value": "0.0", "unit": "mi"},
            "trip_duration": {"value": "02:16"},
            "trip_average_mpg": {"value": "41.20", "unit": "MPG"}})
        self.assertEqual(document["schema_version"], 2)
        self.assertEqual(trip["trip_date"], "2031-06-12")
        for name, data in self.saved.items():
            self.assertFalse((self.source / name).exists())
            self.assertEqual((self.destination / name).read_bytes(), data)

    def test_equal_decimal_ties_choose_lexical_spelling(self):
        capture = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("a.heic", capture, {"trip_distance": ("0.0", "mi")})
        self.photo("b.heic", capture, {"trip_distance": ("-0", "mi")})
        self.assertTrue(self.run_batch().complete)
        self.assertEqual(self.month()["trips"][0]["fields"]["trip_distance"],
                         {"value": "-0", "unit": "mi"})

    def test_conflicting_clear_tie_stops_before_all_business_effects(self):
        capture = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("a.heic", capture, {"trip_distance": ("1", "mi")})
        self.photo("b.heic", capture, {"trip_distance": ("2", "mi")})
        result = self.run_batch()
        self.assertFalse(result.complete)
        self.assert_sources_preserved(self.saved)
        self.assertFalse(list(self.output.glob("????-??.json")))
        self.assertFalse(list(self.destination.glob("*.heic")))
        self.assertIsNotNone(result.report_path)

    def test_first_to_last_window_does_not_chain(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        for index, seconds in enumerate((0, 180, 181)):
            self.photo(f"{index}.heic", start + timedelta(seconds=seconds))
        self.assertTrue(self.run_batch().complete)
        trips = self.month()["trips"]
        self.assertEqual(len(trips), 2)
        self.assertEqual(trips[0]["last_capture_times"], ["2031-06-12T12:03:00+00:00"])
        self.assertEqual(trips[1]["first_capture_times"], ["2031-06-12T12:03:01+00:00"])

    def test_same_month_latest_date_tie_uses_greatest_local_day(self):
        instant = datetime(2031, 6, 12, 23, 30, tzinfo=timezone.utc)
        self.photo("a.heic", instant)
        self.photo("b.heic", instant.astimezone(timezone(timedelta(hours=1))))
        result = self.run_batch()
        self.assertTrue(result.complete)
        self.assertEqual(self.month()["trips"][0]["trip_date"], "2031-06-13")
        self.assertEqual(len(self.month()["trips"][0]["last_capture_times"]), 2)

    def test_cross_month_latest_tie_uses_utc_date_and_month(self):
        instant = datetime(2031, 7, 1, 0, 30, tzinfo=timezone.utc)
        self.photo("a.heic", instant)
        self.photo("b.heic", instant.astimezone(timezone(-timedelta(hours=1))))
        self.assertTrue(self.run_batch().complete)
        trip, = self.month("2031-07")["trips"]
        self.assertEqual(trip["trip_date"], "2031-07-01")
        self.assertEqual(trip["month_assignment"], "latest_instant_utc")
        self.assertFalse((self.output / "2031-06.json").exists())

    def test_collision_keeps_existing_and_already_suffixed_stem(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.destination.mkdir()
        for name in ("photo-01.heic", "photo-01-01.heic"):
            (self.destination / name).write_bytes(b"existing different bytes")
        self.photo("photo-01.heic", start)
        self.assertTrue(self.run_batch().complete)
        self.assertEqual((self.destination / "photo-01.heic").read_bytes(), b"existing different bytes")
        self.assertEqual((self.destination / "photo-01-01.heic").read_bytes(), b"existing different bytes")
        self.assertEqual((self.destination / "photo-01-02.heic").read_bytes(), self.saved["photo-01.heic"])

    def test_exact_repeat_preserves_month_and_repeated_sources(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("a.heic", start)
        self.photo("b.heic", start + timedelta(minutes=1))
        self.assertTrue(self.run_batch().complete)
        before = (self.output / "2031-06.json").read_bytes()
        for name, data in self.saved.items():
            (self.source / name).write_bytes(data)
        self.assertTrue(self.run_batch().complete)
        self.assert_sources_preserved(self.saved)
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before)

    def test_subset_repeat_is_overlap_and_preserves_source(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("a.heic", start)
        self.photo("b.heic", start + timedelta(minutes=1))
        self.assertTrue(self.run_batch().complete)
        before = (self.output / "2031-06.json").read_bytes()
        (self.source / "a.heic").write_bytes(self.saved["a.heic"])
        self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(["a.heic"])
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before)

    def masking_case(self, start):
        self.photo("old.heic", start)
        self.assertTrue(self.run_batch().complete)
        month = start.strftime("%Y-%m")
        before = self.month(month)["trips"][0]
        for minute in (-3, 1, 2, 4, 20):
            self.photo(f"new{minute}.heic", start + timedelta(minutes=minute))
        result = self.run_batch()
        self.assertFalse(result.complete)
        self.assert_sources_preserved([f"new{minute}.heic" for minute in (-3, 1, 2, 4)])
        self.assertFalse((self.source / "new20.heic").exists())
        self.assertEqual(len(self.month(month)["trips"]), 2)
        self.assertEqual(self.month(month)["trips"][0], before)

    def test_rejected_candidate_cannot_shield_second_overlap(self):
        self.masking_case(datetime(2031, 6, 12, 12, tzinfo=timezone.utc))

    def test_overlap_history_is_consulted_across_month_boundary(self):
        self.masking_case(datetime(2031, 7, 1, 0, tzinfo=timezone.utc))

    def test_changed_window_old_only_regrouping_does_not_block_disjoint_trip(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("old0.heic", start)
        self.photo("old3.heic", start + timedelta(minutes=3))
        self.assertTrue(self.run_batch().complete)
        before = self.month()["trips"][0]
        self.photo("new.heic", start + timedelta(minutes=20))
        self.assertTrue(self.run_batch(window=timedelta(minutes=1)).complete)
        self.assertEqual(len(self.month()["trips"]), 2)
        self.assertEqual(self.month()["trips"][0], before)

    def test_shared_asset_loss_after_interpretation_prevents_moves_and_months(self):
        self.photo("a.heic", datetime(2031, 6, 12, 12, tzinfo=timezone.utc))
        def lose_assets(path, assets):
            batch._validate_assets.side_effect = SharedAssetError("model disappeared")
            return self.outcomes[path.name]
        self.interpret.side_effect = lose_assets
        self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(self.saved)
        self.assertFalse(list(self.output.glob("????-??.json")))
        self.assertFalse(list(self.destination.glob("*.heic")))

    def test_individual_failure_and_invalid_timestamp_preserve_sources_and_continue(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        failed = self.photo("failed.heic", start)
        missing = self.photo("missing.heic", start)
        self.photo("good.heic", start + timedelta(minutes=20))
        self.outcomes["failed.heic"] = PhotoInterpretation(failed, "unresolved", issues=(
            InterpretationIssue(failed, "individual native failure", "preserve/report/continue"),))
        original = self.outcomes["missing.heic"]
        self.outcomes["missing.heic"] = PhotoInterpretation(
            missing, original.layout, original.observations, CaptureMetadata("invalid original date", None, None))
        self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(["failed.heic", "missing.heic"])
        self.assertFalse((self.source / "good.heic").exists())
        self.assertEqual(len(self.month()["trips"]), 1)

    def test_source_mutation_during_preflight_is_never_moved(self):
        self.photo("changed.heic", datetime(2031, 6, 12, 12, tzinfo=timezone.utc))
        def mutate(path, assets):
            path.write_bytes(b"changed during interpretation")
            return self.outcomes[path.name]
        self.interpret.side_effect = mutate
        self.assertFalse(self.run_batch().complete)
        self.assertEqual((self.source / "changed.heic").read_bytes(), b"changed during interpretation")
        self.assertFalse(list(self.output.glob("????-??.json")))
        self.assertFalse(list(self.destination.glob("*.heic")))

    def test_external_month_edit_is_preserved_and_blocks_new_effects(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("old.heic", start)
        self.assertTrue(self.run_batch().complete)
        monthly = self.output / "2031-06.json"
        edited = monthly.read_bytes() + b"\n "
        monthly.write_bytes(edited)
        self.photo("new.heic", start + timedelta(minutes=20))
        self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(["new.heic"])
        self.assertEqual(monthly.read_bytes(), edited)

    def test_copy_failure_preserves_trip_and_allows_disjoint_then_recovery_only(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("failed.heic", start)
        self.photo("good.heic", start + timedelta(minutes=20))
        original_copy = batch._copy_file
        def fail_first(source, temporary):
            if source.name == "failed.heic":
                raise OSError("authored copy failure")
            return original_copy(source, temporary)
        with patch.object(batch, "_copy_file", side_effect=fail_first):
            self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(["failed.heic"])
        self.assertFalse((self.source / "good.heic").exists())
        self.assertEqual(len(self.month()["trips"]), 1)
        self.photo("fresh.heic", start + timedelta(minutes=40))
        self.interpret.reset_mock()
        self.assertTrue(self.run_batch(window=timedelta(seconds=0)).complete)
        self.interpret.assert_not_called()
        self.assert_sources_preserved(["fresh.heic"])
        self.assertFalse((self.source / "failed.heic").exists())
        self.assertEqual(len(self.month()["trips"]), 2)
        before = (self.output / "2031-06.json").read_bytes()
        self.assertTrue(self.run_batch().complete)
        self.assertEqual(len(self.month()["trips"]), 3)
        self.assertNotEqual((self.output / "2031-06.json").read_bytes(), before)

    def test_published_copy_before_progress_save_recovers_without_duplicate(self):
        self.photo("a.heic", datetime(2031, 6, 12, 12, tzinfo=timezone.utc))
        original_save = batch._save_state
        def fail_after_publish(output, state, expected):
            pending = state.get("pending")
            if pending and any(file["stage"] == "published"
                               for trip in pending["trips"] for file in trip["files"]):
                raise OSError("authored progress save failure")
            return original_save(output, state, expected)
        with patch.object(batch, "_save_state", side_effect=fail_after_publish):
            self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(["a.heic"])
        self.assertEqual((self.destination / "a.heic").read_bytes(), self.saved["a.heic"])
        self.interpret.reset_mock()
        self.assertTrue(self.run_batch().complete)
        self.interpret.assert_not_called()
        self.assertFalse((self.source / "a.heic").exists())
        self.assertEqual(len(self.month()["trips"]), 1)
        self.assertEqual(sorted(p.name for p in self.destination.glob("*.heic")), ["a.heic"])

    def test_month_replace_before_state_commit_recovers_once(self):
        self.photo("a.heic", datetime(2031, 6, 12, 12, tzinfo=timezone.utc))
        original_write = batch._atomic_write
        def fail_after_month(path, data, expected):
            original_write(path, data, expected)
            if path.name == "2031-06.json":
                raise OSError("authored failure after monthly replacement")
        with patch.object(batch, "_atomic_write", side_effect=fail_after_month):
            self.assertFalse(self.run_batch().complete)
        before = (self.output / "2031-06.json").read_bytes()
        self.assertFalse((self.source / "a.heic").exists())
        self.interpret.reset_mock()
        self.assertTrue(self.run_batch().complete)
        self.interpret.assert_not_called()
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before)
        self.assertEqual(len(self.month()["trips"]), 1)
        self.assertTrue(self.run_batch().complete)
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before)

    def test_changed_remaining_source_during_recovery_is_preserved(self):
        self.photo("a.heic", datetime(2031, 6, 12, 12, tzinfo=timezone.utc))
        with patch.object(batch, "_copy_file", side_effect=OSError("authored failure")):
            self.assertFalse(self.run_batch().complete)
        changed = b"source changed after interrupted run"
        (self.source / "a.heic").write_bytes(changed)
        self.assertFalse(self.run_batch().complete)
        self.assertEqual((self.source / "a.heic").read_bytes(), changed)
        self.assertFalse(list(self.output.glob("????-??.json")))
        state = json.loads((self.output / ".flex-photo-state.json").read_bytes())
        self.assertTrue(state["pending"])

    def test_unexpected_saved_temporary_content_stays_untouched_on_recovery(self):
        self.photo("a.heic", datetime(2031, 6, 12, 12, tzinfo=timezone.utc))
        def fail_copy(source, temporary):
            temporary.write_bytes(b"unexpected private temporary content")
            raise OSError("authored interrupted copy")
        with patch.object(batch, "_copy_file", side_effect=fail_copy):
            self.assertFalse(self.run_batch().complete)
        state = json.loads((self.output / ".flex-photo-state.json").read_bytes())
        temporary = self.destination / state["pending"]["trips"][0]["files"][0]["temporary"]
        before = temporary.read_bytes()
        self.assertTrue(self.run_batch().complete)
        self.assertEqual(temporary.read_bytes(), before)
        self.assertFalse((self.source / "a.heic").exists())
        self.assertEqual((self.destination / "a.heic").read_bytes(), self.saved["a.heic"])
        self.assertEqual(len(self.month()["trips"]), 1)

    def test_unexpected_reserved_destination_is_not_renamed_away_on_recovery(self):
        self.photo("a.heic", datetime(2031, 6, 12, 12, tzinfo=timezone.utc))
        with patch.object(batch, "_copy_file", side_effect=OSError("authored failure")):
            self.assertFalse(self.run_batch().complete)
        unexpected = b"unexpected destination owner"
        (self.destination / "a.heic").write_bytes(unexpected)
        self.assertFalse(self.run_batch().complete)
        self.assertEqual((self.destination / "a.heic").read_bytes(), unexpected)
        self.assertEqual(sorted(p.name for p in self.destination.glob("*.heic")), ["a.heic"])
        self.assert_sources_preserved(["a.heic"])
        self.assertFalse(list(self.output.glob("????-??.json")))

    def test_pending_path_escape_is_rejected_without_touching_outside_file(self):
        self.photo("a.heic", datetime(2031, 6, 12, 12, tzinfo=timezone.utc))
        with patch.object(batch, "_copy_file", side_effect=OSError("authored failure")):
            self.assertFalse(self.run_batch().complete)
        outside = self.root / "outside.heic"
        outside.write_bytes(self.saved["a.heic"])
        state_path = self.output / ".flex-photo-state.json"
        state = json.loads(state_path.read_bytes())
        state["pending"]["trips"][0]["files"][0]["source"] = "../outside.heic"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertFalse(self.run_batch().complete)
        self.assertEqual(outside.read_bytes(), self.saved["a.heic"])
        self.assert_sources_preserved(["a.heic"])
        self.assertFalse(list(self.destination.glob("*.heic")))
        self.assertFalse(list(self.output.glob("????-??.json")))

    def test_recovery_rechecks_month_before_moving_remaining_source(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("old.heic", start)
        self.assertTrue(self.run_batch().complete)
        self.photo("pending.heic", start + timedelta(minutes=20))
        with patch.object(batch, "_copy_file", side_effect=OSError("authored failure")):
            self.assertFalse(self.run_batch().complete)
        monthly = self.output / "2031-06.json"
        external = monthly.read_bytes() + b"\n "
        monthly.write_bytes(external)
        self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(["pending.heic"])
        self.assertFalse((self.destination / "pending.heic").exists())
        self.assertEqual(monthly.read_bytes(), external)

    def test_pending_entry_schema_is_validated_before_recovery_effects(self):
        self.photo("a.heic", datetime(2031, 6, 12, 12, tzinfo=timezone.utc))
        with patch.object(batch, "_copy_file", side_effect=OSError("authored failure")):
            self.assertFalse(self.run_batch().complete)
        state_path = self.output / ".flex-photo-state.json"
        state = json.loads(state_path.read_bytes())
        state["pending"]["trips"][0]["entry"]["fields"]["excluded_dashboard_field"] = {
            "value": "authored invalid state", "unit": None}
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(["a.heic"])
        self.assertFalse(list(self.destination.glob("*.heic")))
        self.assertFalse(list(self.output.glob("????-??.json")))

    def test_existing_month_after_publication_recovery_is_valid_and_idempotent(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("old.heic", start)
        self.assertTrue(self.run_batch().complete)
        old_entry = self.month()["trips"][0]
        self.photo("new.heic", start + timedelta(minutes=20))
        original_write = batch._atomic_write
        def fail_after_month(path, data, expected):
            original_write(path, data, expected)
            if path.name == "2031-06.json":
                raise OSError("authored failure after append replacement")
        with patch.object(batch, "_atomic_write", side_effect=fail_after_month):
            self.assertFalse(self.run_batch().complete)
        before = (self.output / "2031-06.json").read_bytes()
        self.assertEqual(len(self.month()["trips"]), 2)
        self.assertFalse((self.source / "new.heic").exists())
        original_save = batch._save_state
        def interrupt_recovery_save(output, state, expected):
            original_save(output, state, expected)
            pending = state.get("pending")
            if pending and any(trip.get("publication") for trip in pending["trips"]):
                raise OSError("authored second interruption during publication recovery")
        with patch.object(batch, "_save_state", side_effect=interrupt_recovery_save):
            self.assertFalse(self.run_batch().complete)
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before)
        self.interpret.reset_mock()
        self.assertTrue(self.run_batch().complete)
        self.interpret.assert_not_called()
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before)
        self.assertEqual(self.month()["trips"][0], old_entry)
        self.assertTrue(self.run_batch().complete)
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before)

    def test_pending_capture_bounds_must_match_saved_membership(self):
        self.photo("a.heic", datetime(2031, 6, 12, 12, tzinfo=timezone.utc))
        with patch.object(batch, "_copy_file", side_effect=OSError("authored failure")):
            self.assertFalse(self.run_batch().complete)
        state_path = self.output / ".flex-photo-state.json"
        state = json.loads(state_path.read_bytes())
        state["pending"]["trips"][0]["entry"]["first_capture_times"] = ["2031-06-11T12:00:00+00:00"]
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(["a.heic"])
        self.assertFalse(list(self.destination.glob("*.heic")))
        self.assertFalse(list(self.output.glob("????-??.json")))

    def test_pending_duplicate_membership_is_rejected_before_movement(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("a.heic", start)
        self.photo("b.heic", start + timedelta(minutes=1))
        with patch.object(batch, "_copy_file", side_effect=OSError("authored failure")):
            self.assertFalse(self.run_batch().complete)
        state_path = self.output / ".flex-photo-state.json"
        state = json.loads(state_path.read_bytes())
        trip = state["pending"]["trips"][0]
        trip["hashes"][1] = trip["hashes"][0]
        trip["files"][1]["hash"] = trip["hashes"][0]
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(["a.heic", "b.heic"])
        self.assertFalse(list(self.destination.glob("*.heic")))
        self.assertFalse(list(self.output.glob("????-??.json")))

    def test_committed_excluded_field_is_rejected_even_with_matching_hashes(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("old.heic", start)
        self.assertTrue(self.run_batch().complete)
        monthly_path = self.output / "2031-06.json"
        monthly = self.month()
        monthly["trips"][0]["fields"]["excluded_authored_field"] = {"value": "authored", "unit": None}
        edited = batch._json_bytes(monthly)
        monthly_path.write_bytes(edited)
        state_path = self.output / ".flex-photo-state.json"
        state = json.loads(state_path.read_bytes())
        state["months"]["2031-06"] = batch._hash_bytes(edited)
        state["committed"][0]["entry_digest"] = batch._hash_bytes(batch._json_bytes(monthly["trips"][0]))
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.photo("new.heic", start + timedelta(minutes=20))
        self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(["new.heic"])
        self.assertFalse((self.destination / "new.heic").exists())
        self.assertEqual(monthly_path.read_bytes(), edited)

    def test_failed_publication_blocks_same_month_dependents_and_recovers_each_once(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("first.heic", start)
        self.photo("dependent.heic", start + timedelta(minutes=20))
        self.photo("independent.heic", datetime(2031, 7, 1, 12, tzinfo=timezone.utc))
        original_write = batch._atomic_write
        failed = False
        def fail_first_june_before_write(path, data, expected):
            nonlocal failed
            if path.name == "2031-06.json" and not failed:
                failed = True
                raise OSError("authored first publication failure before replacement")
            return original_write(path, data, expected)
        with patch.object(batch, "_atomic_write", side_effect=fail_first_june_before_write):
            self.assertFalse(self.run_batch().complete)
        self.assertTrue(failed)
        self.assertFalse((self.source / "first.heic").exists())
        self.assert_sources_preserved(["dependent.heic"])
        self.assertFalse((self.destination / "dependent.heic").exists())
        self.assertFalse((self.output / "2031-06.json").exists())
        self.assertFalse((self.source / "independent.heic").exists())
        self.assertEqual(len(self.month("2031-07")["trips"]), 1)
        july_before = (self.output / "2031-07.json").read_bytes()
        self.interpret.reset_mock()
        self.assertTrue(self.run_batch().complete)
        self.interpret.assert_not_called()
        june = self.month()["trips"]
        self.assertEqual([trip["first_capture_times"] for trip in june], [
            ["2031-06-12T12:00:00+00:00"], ["2031-06-12T12:20:00+00:00"]])
        self.assertFalse((self.source / "dependent.heic").exists())
        june_before = (self.output / "2031-06.json").read_bytes()
        self.assertTrue(self.run_batch().complete)
        self.assertEqual((self.output / "2031-06.json").read_bytes(), june_before)
        self.assertEqual((self.output / "2031-07.json").read_bytes(), july_before)

    def test_recovery_handles_failed_publisher_later_in_pending_order(self):
        start = datetime(2031, 6, 12, 12, tzinfo=timezone.utc)
        self.photo("earlier.heic", start)
        self.photo("publisher.heic", start + timedelta(minutes=20))
        original_copy = batch._copy_file
        original_write = batch._atomic_write
        def fail_earlier_copy(source, temporary):
            if source.name == "earlier.heic":
                raise OSError("authored earlier movement failure")
            return original_copy(source, temporary)
        def fail_publication(path, data, expected):
            if path.name == "2031-06.json":
                raise OSError("authored later publication failure before replacement")
            return original_write(path, data, expected)
        with patch.object(batch, "_copy_file", side_effect=fail_earlier_copy), \
             patch.object(batch, "_atomic_write", side_effect=fail_publication):
            self.assertFalse(self.run_batch().complete)
        self.assert_sources_preserved(["earlier.heic"])
        self.assertFalse((self.source / "publisher.heic").exists())
        self.assertFalse((self.output / "2031-06.json").exists())
        self.interpret.reset_mock()
        self.run_batch()
        self.assertTrue(self.run_batch().complete)
        self.interpret.assert_not_called()
        trips = self.month()["trips"]
        self.assertEqual(len(trips), 2)
        self.assertEqual({tuple(trip["first_capture_times"]) for trip in trips}, {
            ("2031-06-12T12:00:00+00:00",), ("2031-06-12T12:20:00+00:00",)})
        self.assertFalse((self.source / "earlier.heic").exists())
        before = (self.output / "2031-06.json").read_bytes()
        self.assertTrue(self.run_batch().complete)
        self.assertEqual((self.output / "2031-06.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
