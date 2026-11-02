"""Durable fallback boundaries with injected responses; no network or inference."""
import copy
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from flex_photo.cloud_access import CloudUnavailable, KnownRequestRejected
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

    def test_rejected_request_retains_safe_service_diagnostic_and_completed_view_on_resume(self):
        diagnostic = {'operation': 'inference', 'http_status': 429,
                      'service_code': 'rate_limit_exceeded', 'response_shape': 'error_object',
                      'request_id': 'req_' + 'a' * 32, 'message': 'private bearer secret'}
        first = Mock()
        first.recognize.side_effect = [responses(self.case)[0],
                                      KnownRequestRejected('unavailable', diagnostic=diagnostic)]
        initial = self.flow(first)
        _, pending, reason = initial.recover(self.path, 'photo.heic', self.digest, self.photo)
        self.assertTrue(pending)
        self.assertEqual(reason, 'unavailable')
        issue, action = initial.failure_description(reason)
        self.assertIn('http_status=429', issue)
        self.assertIn('service_code=rate_limit_exceeded', issue)
        self.assertIn('request_state=rejected', issue)
        self.assertIn('not confirmed subscription exhaustion', action)
        state = initial.journal.results['photo.heic']['result']
        self.assertNotIn('message', state['failure'])
        self.assertEqual(state['failure']['request_state'], 'rejected')
        rejected = next(r for r in state['requests'].values() if r['status'] == 'rejected')
        self.assertEqual(rejected['diagnostic'], state['failure'])
        self.assertNotIn('private bearer secret', str(state))
        second = Mock()
        second.recognize.return_value = responses(self.case)[1]
        _, pending, _ = self.flow(second, resume=True).recover(
            self.path, 'photo.heic', self.digest, self.photo)
        self.assertFalse(pending)
        second.recognize.assert_called_once()

    def test_preflight_failure_is_durable_without_dispatch_and_unknown_stays_no_repeat(self):
        first = Mock()
        first.check_available.side_effect = CloudUnavailable('network', diagnostic={
            'operation': 'token_refresh', 'exception_type': 'TimeoutError'})
        initial = self.flow(first)
        _, pending, reason = initial.recover(self.path, 'photo.heic', self.digest, self.photo)
        self.assertTrue(pending)
        first.recognize.assert_not_called()
        state = initial.journal.results['photo.heic']['result']
        self.assertEqual(state['failure'], {'operation': 'token_refresh',
                         'exception_type': 'TimeoutError', 'request_state': 'not_sent'})
        self.assertEqual(state['requests'], {})
        uncertain = Mock()
        uncertain.recognize.side_effect = CloudUnavailable('unknown_outcome', diagnostic={
            'operation': 'inference', 'exception_type': 'TimeoutError'})
        flow = self.flow(uncertain, resume=True)
        flow.recover(self.path, 'photo.heic', self.digest, self.photo)
        never = Mock()
        resumed = self.flow(never, resume=True)
        _, pending, reason = resumed.recover(self.path, 'photo.heic', self.digest, self.photo)
        issue, action = resumed.failure_description(reason)
        self.assertIn('operation=inference', issue)
        self.assertIn('exception_type=TimeoutError', issue)
        self.assertIn('request_state=unknown', issue)
        self.assertIn('do not repeat', action)
        never.recognize.assert_not_called()

    def test_local_crop_failure_does_not_inherit_another_photos_service_diagnostic(self):
        other = self.root / 'other.heic'
        third = self.root / 'third.heic'
        other.write_bytes(b'authored other source')
        third.write_bytes(b'authored third source')
        first = Mock()
        first.recognize.side_effect = KnownRequestRejected('unavailable', diagnostic={
            'operation': 'inference', 'http_status': 429, 'service_code': 'rate_limit_exceeded',
            'request_id': 'req_' + 'c' * 32})
        flow = GptFallback(self.output, {'recipe_version': 4},
                           ['photo.heic', 'other.heic', 'third.heic'], self.assets, first)
        flow.recover(self.path, 'photo.heic', self.digest, self.photo)
        original_diagnostic = flow.last_diagnostic.copy()
        self.worker.side_effect = None
        self.worker.return_value = {'error': 'native worker failed'}
        _, pending, reason = flow.recover(other, 'other.heic', hashlib.sha256(other.read_bytes()).hexdigest(),
                                          replace(self.photo, path=other))
        self.assertTrue(pending)
        self.assertEqual(reason, 'local_crop_failure')
        issue, action = flow.failure_description(reason)
        self.assertNotIn('http_status', issue)
        self.assertNotIn('request_id', action)
        self.assertIn('no image sent', action)
        self.worker.return_value = {'fallback_candidates': [copy.deepcopy(self.case)]}
        _, pending, reason = flow.recover(third, 'third.heic', hashlib.sha256(third.read_bytes()).hexdigest(),
                                          replace(self.photo, path=third))
        self.assertTrue(pending)
        self.assertEqual(reason, 'unavailable')
        self.assertEqual(flow.last_diagnostic, original_diagnostic)
        first.recognize.assert_called_once()

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
        first.check_available.side_effect = CloudUnavailable("authentication")
        recovered, pending, reason = self.flow(first).recover(
            self.path, "photo.heic", self.digest, self.photo)
        self.assertTrue(pending)
        self.assertEqual(reason, "authentication")
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

    def test_validation_profile_change_reuses_completed_requests_and_revalidates_locally(self):
        # Inject a bad derived measurement while keeping source and request
        # pixels/settings unchanged; this is cache behavior, not OCR evidence.
        self.case["pixel_evidence"]["colons"] = 2
        first = Mock()
        first.recognize.side_effect = responses(self.case)
        original, pending, _ = self.flow(first).recover(
            self.path, "photo.heic", self.digest, self.photo)
        self.assertFalse(pending)
        self.assertEqual(first.recognize.call_count, 2)
        self.assertEqual(original.observations[1].status, "unclear")
        self.case["pixel_evidence"]["colons"] = 1
        second = Mock()
        recovered, pending, _ = self.flow(second, resume=True).recover(
            self.path, "photo.heic", self.digest, self.photo)
        second.recognize.assert_not_called()
        self.assertFalse(pending)
        self.assertEqual(recovered.observations[1].value, "02:14")
