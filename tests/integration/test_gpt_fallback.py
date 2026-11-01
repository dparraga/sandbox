"""Batch effects and durable fallback with injected native/cloud boundaries."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from flex_photo import batch
from flex_photo.cloud_access import CloudClient
from flex_photo.interpretation import FieldObservation, InterpretationAssets, PhotoInterpretation
from flex_photo.metadata import CaptureMetadata
from tests.unit.test_fallback import candidate, responses


class GptBatchIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="flex gpt batch ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source, self.destination, self.output = [self.root / name for name in ("source", "destination", "output")]
        self.source.mkdir()
        self.assets = InterpretationAssets(Path("engine"), Path("models"), "a" * 64)
        self.outcomes, self.originals = {}, {}
        self.case = candidate()
        assets = patch.object(batch, "_validate_assets")
        assets.start()
        self.addCleanup(assets.stop)
        interpreter = patch.object(batch, "interpret_photo", side_effect=lambda path, *a, **k: self.outcomes[path.name])
        self.local = interpreter.start()
        self.addCleanup(interpreter.stop)
        worker = patch("flex_photo._interpretation_worker.run_bounded",
                       side_effect=lambda *a, **k: {"fallback_candidates": [copy.deepcopy(self.case)]})
        self.crops = worker.start()
        self.addCleanup(worker.stop)

    def photo(self, name, minute, *, unresolved=False, excluded=False):
        path = self.source / name
        self.originals[name] = ("authored original " + name).encode()
        path.write_bytes(self.originals[name])
        if excluded:
            self.outcomes[name] = PhotoInterpretation(path, "excluded")
        else:
            self.outcomes[name] = PhotoInterpretation(path, "drive_info", (
                FieldObservation("trip_distance", "clear", value="17.0", unit="mi"),
                FieldObservation("trip_duration", "unclear") if unresolved else
                FieldObservation("trip_duration", "clear", value="01:00"),
                FieldObservation("trip_average_mpg", "absent"),
                FieldObservation("odometer", "absent"),
            ), CaptureMetadata(f"2031:06:12 12:{minute:02}:00", "+00:00", None))
        return path

    def run_batch(self, client, *, resume=False):
        return batch.process_batch(self.source, self.destination, self.output,
                                   assets=self.assets, window=timedelta(minutes=3),
                                   gpt_fallback=True, cloud_client=client, resume=resume)

    def test_recovery_preserves_primary_value_and_publishes_existing_monthly_contract(self):
        self.photo("a.heic", 0, unresolved=True)
        self.photo("clear.heic", 10)
        self.photo("oversize.heic", 20, excluded=True)
        client = Mock()
        client.recognize.side_effect = responses(self.case)
        result = self.run_batch(client)
        self.assertTrue(result.complete)
        self.assertEqual(client.recognize.call_count, 2)
        self.assertEqual(self.crops.call_count, 1)
        month = json.loads((self.output / "2031-06.json").read_bytes())
        self.assertEqual(month["trips"][0]["fields"]["trip_distance"], {"value": "17.0", "unit": "mi"})
        self.assertEqual(month["trips"][0]["fields"]["trip_duration"], {"value": "02:14"})
        for name in ("a.heic", "clear.heic"):
            self.assertEqual((self.destination / name).read_bytes(), self.originals[name])
        self.assertEqual((self.source / "oversize.heic").read_bytes(), self.originals["oversize.heic"])
        report = json.loads(result.report_path.read_bytes())
        self.assertFalse(any(issue["item"] == "oversize.heic" for issue in report["issues"]))

    def test_default_cloud_block_preserves_pending_original_and_independent_local_effects(self):
        pending = self.photo("pending.heic", 0, unresolved=True)
        self.photo("clear.heic", 10)
        first = self.run_batch(CloudClient())
        self.assertFalse(first.complete)
        self.assertEqual(pending.read_bytes(), self.originals["pending.heic"])
        self.assertEqual((self.destination / "clear.heic").read_bytes(), self.originals["clear.heic"])
        self.assertTrue((self.output / ".flex-photo-checkpoint").is_dir())
        self.local.reset_mock()
        client = Mock()
        client.recognize.side_effect = responses(self.case)
        second = self.run_batch(client, resume=True)
        self.assertTrue(second.complete)
        self.local.assert_not_called()
        self.assertEqual(client.recognize.call_count, 2)
        self.assertEqual((self.destination / "pending.heic").read_bytes(), self.originals["pending.heic"])
        month = json.loads((self.output / "2031-06.json").read_bytes())
        self.assertEqual(len(month["trips"]), 2)

    def test_photo_average_includes_new_crop_and_cloud_work(self):
        self.photo("a.heic", 0, unresolved=True)
        clock = [0.0]
        def local(path, *args, **kwargs):
            clock[0] += 2
            return self.outcomes[path.name]
        def crops(*args, **kwargs):
            clock[0] += 1
            return {"fallback_candidates": [copy.deepcopy(self.case)]}
        replies = iter(responses(self.case))
        def recognize(request):
            clock[0] += 5
            return next(replies)
        self.local.side_effect = local
        self.crops.side_effect = crops
        client = Mock()
        client.recognize.side_effect = recognize
        progresses = []
        progress_type = batch.Progress
        def progress(*args, **kwargs):
            instance = progress_type(*args, **kwargs, clock=lambda: clock[0])
            progresses.append(instance)
            return instance
        with patch.object(batch.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(batch, "Progress", side_effect=progress):
            result = self.run_batch(client)
        self.assertTrue(result.complete)
        snapshot = progresses[0].snapshot()
        self.assertEqual(snapshot["processed_count"], 1)
        self.assertEqual(snapshot["processed_seconds"], 13)
        self.assertEqual(snapshot["average_seconds"], 13)

    def test_pending_member_does_not_publish_or_move_a_partial_trip(self):
        self.photo("pending.heic", 0, unresolved=True)
        self.photo("clear.heic", 1)
        first = self.run_batch(CloudClient())
        self.assertFalse(first.complete)
        for name in ("pending.heic", "clear.heic"):
            self.assertEqual((self.source / name).read_bytes(), self.originals[name])
        self.assertFalse(list(self.output.glob("20??-??.json")))
        self.local.reset_mock()
        client = Mock()
        client.recognize.side_effect = responses(self.case)
        second = self.run_batch(client, resume=True)
        self.assertTrue(second.complete)
        self.local.assert_not_called()
        self.assertEqual(second.counts["moved"], 2)
        month = json.loads((self.output / "2031-06.json").read_bytes())
        self.assertEqual(len(month["trips"]), 1)
        self.assertEqual(month["trips"][0]["fields"]["trip_duration"], {"value": "01:00"})

    def test_pending_group_retains_first_to_last_window_without_chaining(self):
        self.photo("pending.heic", 0, unresolved=True)
        self.photo("neighbor.heic", 2)
        self.photo("independent.heic", 4)
        result = self.run_batch(CloudClient())
        self.assertFalse(result.complete)
        for name in ("pending.heic", "neighbor.heic"):
            self.assertEqual((self.source / name).read_bytes(), self.originals[name])
        self.assertEqual((self.destination / "independent.heic").read_bytes(), self.originals["independent.heic"])
        self.assertEqual(result.counts["trips"], 1)
