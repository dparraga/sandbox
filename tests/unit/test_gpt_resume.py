"""Durable fallback boundaries with injected responses; no network or inference."""
import copy
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from flex_photo.cloud_access import CloudUnavailable
from flex_photo.gpt_flow import GptFallback
from flex_photo.interpretation import CropEvidence, FieldObservation, InterpretationAssets, PhotoInterpretation
from tests.unit.test_fallback import candidate, responses


class Interrupted(BaseException):
    pass


class GptResumeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="flex gpt resume ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "output"
        self.output.mkdir()
        self.path = self.root / "photo.heic"
        self.path.write_bytes(b"authored source bytes; native crop worker is injected")
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assets = InterpretationAssets(Path("engine"), Path("models"), "a" * 64)
        self.case = candidate()
        self.photo = PhotoInterpretation(self.path, "drive_info", (
            FieldObservation("trip_distance", "clear", value="17.0", unit="mi"),
            FieldObservation("trip_duration", "unclear"),
            FieldObservation("trip_average_mpg", "absent"),
            FieldObservation("odometer", "absent"),
        ))
        worker = patch("flex_photo._interpretation_worker.run_bounded",
                       side_effect=lambda *a, **k: {"fallback_candidates": [copy.deepcopy(self.case)]})
        self.worker = worker.start()
        self.addCleanup(worker.stop)

    def flow(self, client, **kwargs):
        return GptFallback(self.output, {"recipe_version": 4}, ["photo.heic"],
                           self.assets, client, **kwargs)

    def test_completed_first_view_survives_pause_and_is_not_repeated(self):
        first = Mock()
        first.recognize.return_value = responses(self.case)[0]
        def pause_after_saved_view():
            if first.recognize.call_count:
                raise Interrupted()
        flow = self.flow(first, boundary=pause_after_saved_view)
        with self.assertRaises(Interrupted):
            flow.recover(self.path, "photo.heic", self.digest, self.photo)
        second = Mock()
        second.recognize.return_value = responses(self.case)[1]
        recovered, pending, reason = self.flow(second, resume=True).recover(
            self.path, "photo.heic", self.digest, self.photo)
        self.assertEqual(second.recognize.call_count, 1)
        self.assertFalse(pending)
        self.assertIsNone(reason)
        observations = {o.field_id: o for o in recovered.observations}
        self.assertEqual(observations["trip_duration"].value, "02:14")
        self.assertEqual(observations["trip_distance"], self.photo.observations[0])
        third = Mock()
        again, pending, _ = self.flow(third, resume=True).recover(
            self.path, "photo.heic", self.digest, self.photo)
        third.recognize.assert_not_called()
        self.assertEqual(again.observations, recovered.observations)
        self.assertFalse(pending)

    def test_interrupted_dispatch_remains_unknown_and_never_repeats(self):
        first = Mock()
        first.recognize.side_effect = Interrupted()
        initial = self.flow(first)
        initial.remember_primary("photo.heic", self.digest, self.photo)
        with self.assertRaises(Interrupted):
            initial.recover(self.path, "photo.heic", self.digest, self.photo)
        second = Mock()
        resumed = self.flow(second, resume=True)
        recovered, pending, reason = resumed.recover(
            self.path, "photo.heic", self.digest, self.photo)
        self.assertTrue(pending)
        self.assertEqual(reason, "unknown_outcome")
        self.assertEqual(recovered.observations, self.photo.observations)
        self.assertTrue(resumed.has_pending())
        second.recognize.assert_not_called()
        self.worker.side_effect = None
        self.worker.return_value = {"fallback_candidates": []}
        third = Mock()
        _, pending, reason = self.flow(third, resume=True).recover(
            self.path, "photo.heic", self.digest, self.photo)
        self.assertTrue(pending)
        self.assertEqual(reason, "unknown_outcome")
        third.recognize.assert_not_called()

    def test_preflight_unavailability_can_resume_without_losing_local_clear_values(self):
        first = Mock()
        first.check_available.side_effect = CloudUnavailable("quota")
        recovered, pending, reason = self.flow(first).recover(
            self.path, "photo.heic", self.digest, self.photo)
        self.assertTrue(pending)
        self.assertEqual(reason, "quota")
        first.recognize.assert_not_called()
        self.assertEqual(recovered.observations, self.photo.observations)
        second = Mock()
        second.recognize.side_effect = responses(self.case)
        recovered, pending, _ = self.flow(second, resume=True).recover(
            self.path, "photo.heic", self.digest, self.photo)
        self.assertEqual(second.recognize.call_count, 2)
        self.assertFalse(pending)
        self.assertEqual(recovered.observations[1].value, "02:14")

    def test_invalid_response_is_terminal_without_a_later_extra_view_request(self):
        first = Mock()
        first.recognize.side_effect = CloudUnavailable("invalid_response")
        _, pending, _ = self.flow(first).recover(self.path, "photo.heic", self.digest, self.photo)
        self.assertFalse(pending)
        self.assertEqual(first.recognize.call_count, 1)
        second = Mock()
        _, pending, _ = self.flow(second, resume=True).recover(
            self.path, "photo.heic", self.digest, self.photo)
        second.recognize.assert_not_called()
        self.assertFalse(pending)

    def test_original_complete_conflict_survives_scalar_primary_cache(self):
        original = replace(self.photo, observations=tuple(
            replace(o, evidence=(CropEvidence((10, 20, 145, 65), ("03:14",), (0,)),))
            if o.field_id == "trip_duration" else o for o in self.photo.observations))
        first = self.flow(Mock())
        first.remember_primary("photo.heic", self.digest, original)
        client = Mock()
        client.recognize.side_effect = responses(self.case)
        recovered, pending, _ = self.flow(client, resume=True).recover(
            self.path, "photo.heic", self.digest, self.photo)
        self.assertFalse(pending)
        self.assertEqual(client.recognize.call_count, 2)
        self.assertEqual(recovered.observations[1].status, "unclear")

    def test_source_changed_during_crop_preparation_is_never_uploaded(self):
        def prepare_changed_source(*args, **kwargs):
            self.path.write_bytes(b"changed during crop preparation")
            return {"fallback_candidates": [copy.deepcopy(self.case)]}
        self.worker.side_effect = prepare_changed_source
        client = Mock()
        with self.assertRaisesRegex(ValueError, "source changed"):
            self.flow(client).recover(self.path, "photo.heic", self.digest, self.photo)
        client.recognize.assert_not_called()

    def test_native_crop_failure_remains_pending_without_cloud_dispatch(self):
        self.worker.return_value = {"error": "individual decode/OCR/resource failure: RuntimeError"}
        self.worker.side_effect = None
        client = Mock()
        flow = self.flow(client)
        recovered, pending, reason = flow.recover(
            self.path, "photo.heic", self.digest, self.photo)
        self.assertEqual(recovered, self.photo)
        self.assertTrue(pending)
        self.assertEqual(reason, "local_crop_failure")
        self.assertTrue(flow.has_pending())
        client.check_available.assert_not_called()
        client.recognize.assert_not_called()
        restored = self.flow(Mock(), resume=True)
        self.assertTrue(restored.has_pending())
        self.worker.return_value = {"fallback_candidates": []}
        recovered, pending, reason = restored.recover(
            self.path, "photo.heic", self.digest, self.photo)
        self.assertEqual(recovered, self.photo)
        self.assertFalse(pending)
        self.assertIsNone(reason)
        self.assertFalse(restored.has_pending())
