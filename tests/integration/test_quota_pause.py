"""Subscription-limit pause and manual recovery; all cloud responses are injected."""
import json
import unittest
from unittest.mock import Mock, patch

from flex_photo.cloud_access import CloudUnavailable, KnownRequestRejected
from flex_photo.gpt_flow import GptFallback
from tests.integration import test_gpt_fallback as fixtures
from tests.unit.test_fallback import responses


class QuotaPauseTests(unittest.TestCase):
    setUp = fixtures.GptBatchIntegrationTests.setUp
    photo = fixtures.GptBatchIntegrationTests.photo
    run_batch = fixtures.GptBatchIntegrationTests.run_batch

    def assert_paused_without_effects(self, result):
        self.assertEqual(result.status, "paused")
        for name, original in self.originals.items():
            self.assertEqual((self.source / name).read_bytes(), original)
        self.assertFalse(list(self.output.glob("20??-??.json")))
        self.assertFalse(list(self.destination.glob("*.heic")))
        self.assertTrue((self.output / ".flex-photo-checkpoint").is_dir())
        self.assertTrue((self.output / ".flex-photo-gpt/.flex-photo-checkpoint").is_dir())
        report = json.loads(result.report_path.read_bytes())
        self.assertEqual(report["status"], "paused")
        self.assertTrue(any("subscription limit" in issue["issue"].lower()
                            for issue in report["issues"]))

    def test_preflight_limit_pauses_before_next_photo_and_manual_resume_reuses_local_work(self):
        self.photo("a.heic", 0, unresolved=True)
        self.photo("z.heic", 10)
        limited = Mock()
        limited.check_available.side_effect = CloudUnavailable("quota")
        first = self.run_batch(limited)
        self.assert_paused_without_effects(first)
        self.assertEqual([call.args[0].name for call in self.local.call_args_list], ["a.heic"])
        limited.recognize.assert_not_called()
        self.local.reset_mock()
        renewed = Mock()
        renewed.recognize.side_effect = responses(self.case)
        resumed = self.run_batch(renewed, resume=True)
        self.assertTrue(resumed.complete)
        self.assertEqual([call.args[0].name for call in self.local.call_args_list], ["z.heic"])
        self.assertEqual(renewed.recognize.call_count, 2)
        self.assertEqual(resumed.counts["moved"], 2)

    def test_rejected_second_view_pauses_and_resume_reuses_completed_first_view(self):
        self.photo("a.heic", 0, unresolved=True)
        self.photo("z.heic", 1)
        limited = Mock()
        limited.recognize.side_effect = [responses(self.case)[0], CloudUnavailable("quota")]
        first = self.run_batch(limited)
        self.assert_paused_without_effects(first)
        self.assertEqual(limited.recognize.call_count, 2)
        self.assertEqual([call.args[0].name for call in self.local.call_args_list], ["a.heic"])
        self.local.reset_mock()
        renewed = Mock()
        renewed.recognize.return_value = responses(self.case)[1]
        resumed = self.run_batch(renewed, resume=True)
        self.assertTrue(resumed.complete)
        self.assertEqual(renewed.recognize.call_count, 1)
        self.assertEqual([call.args[0].name for call in self.local.call_args_list], ["z.heic"])
        self.assertEqual(resumed.counts["moved"], 2)
        month = json.loads((self.output / "2031-06.json").read_bytes())
        self.assertEqual(len(month["trips"]), 1)
        self.assertEqual(month["trips"][0]["fields"]["trip_duration"], {"value": "01:00"})

    def test_uncertain_dispatch_is_not_quota_and_never_repeats_on_manual_resume(self):
        self.photo("a.heic", 0, unresolved=True)
        uncertain = Mock()
        uncertain.recognize.side_effect = CloudUnavailable("unknown_outcome")
        first = self.run_batch(uncertain)
        self.assertEqual(first.status, "incomplete")
        self.local.reset_mock()
        renewed = Mock()
        second = self.run_batch(renewed, resume=True)
        self.assertEqual(second.status, "incomplete")
        self.local.assert_not_called()
        renewed.recognize.assert_not_called()
        self.assertEqual((self.source / "a.heic").read_bytes(), self.originals["a.heic"])

    def test_known_auth_rejection_retries_only_rejected_view_after_manual_resume(self):
        self.photo("a.heic", 0, unresolved=True)
        rejected = Mock()
        rejected.recognize.side_effect = [responses(self.case)[0], KnownRequestRejected("authentication")]
        first = self.run_batch(rejected)
        self.assertEqual(first.status, "incomplete")
        self.assertEqual((self.source / "a.heic").read_bytes(), self.originals["a.heic"])
        self.local.reset_mock()
        renewed = Mock()
        renewed.recognize.return_value = responses(self.case)[1]
        second = self.run_batch(renewed, resume=True)
        self.assertTrue(second.complete)
        self.local.assert_not_called()
        renewed.recognize.assert_called_once()
        month = json.loads((self.output / "2031-06.json").read_bytes())
        self.assertEqual(month["trips"][0]["fields"]["trip_duration"], {"value": "02:14"})

    def test_uncertain_auth_failure_cannot_be_retried_as_a_known_rejection(self):
        self.photo("a.heic", 0, unresolved=True)
        uncertain = Mock()
        uncertain.recognize.side_effect = [responses(self.case)[0], CloudUnavailable("authentication")]
        first = self.run_batch(uncertain)
        self.assertEqual(first.status, "incomplete")
        self.local.reset_mock()
        renewed = Mock()
        second = self.run_batch(renewed, resume=True)
        self.assertEqual(second.status, "incomplete")
        self.local.assert_not_called()
        renewed.recognize.assert_not_called()
        self.assertEqual((self.source / "a.heic").read_bytes(), self.originals["a.heic"])

    def test_invalid_output_is_reported_separately_and_request_schema_does_not_force_truth(self):
        self.photo("a.heic", 0, unresolved=True)
        client = Mock()
        client.recognize.side_effect = CloudUnavailable("invalid_response")
        result = self.run_batch(client)
        client.recognize.assert_called_once()
        report = json.loads(result.report_path.read_bytes())
        issues = [issue["issue"].lower() for issue in report["issues"] if issue.get("stage") == "fallback"]
        self.assertTrue(any("invalid" in issue and "response" in issue for issue in issues))
        self.assertFalse(any("crop" in issue or "network" in issue for issue in issues))
        request = client.recognize.call_args.args[0]
        output_format = request["text"]["format"]
        self.assertEqual(output_format["type"], "json_schema")
        self.assertTrue(output_format["strict"])
        schema = output_format["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        for name in ("title_text", "field_label_text", "value_text", "unit_text"):
            self.assertEqual(schema["properties"][name], {"type": ["string", "null"]})
        self.assertNotIn("02:14", json.dumps(request))

    def test_changed_source_supersedes_never_dispatched_pending_without_stale_incomplete_state(self):
        self.photo("a.heic", 0, unresolved=True)
        unavailable = Mock()
        unavailable.check_available.side_effect = CloudUnavailable("authentication")
        first = self.run_batch(unavailable)
        self.assertEqual(first.status, "incomplete")
        unavailable.recognize.assert_not_called()
        previous_report = first.report_path.read_bytes()
        journal = self.output / ".flex-photo-gpt/.flex-photo-checkpoint/results.jsonl"
        previous_journal = journal.read_bytes()
        self.photo("a.heic", 0)
        revised = b"authored changed source now independently clear in local interpretation"
        (self.source / "a.heic").write_bytes(revised)
        self.originals["a.heic"] = revised
        self.local.reset_mock()
        renewed = Mock()
        finish = GptFallback.finish
        def verify_history_then_finish(flow):
            self.assertTrue(journal.read_bytes().startswith(previous_journal))
            return finish(flow)
        with patch.object(GptFallback, "finish", new=verify_history_then_finish):
            second = self.run_batch(renewed, resume=True)
        self.assertTrue(second.complete)
        self.assertEqual([call.args[0].name for call in self.local.call_args_list], ["a.heic"])
        renewed.recognize.assert_not_called()
        self.assertEqual((self.destination / "a.heic").read_bytes(), revised)
        self.assertEqual(first.report_path.read_bytes(), previous_report)
        self.assertFalse((self.output / ".flex-photo-checkpoint").exists())
        self.assertFalse((self.output / ".flex-photo-gpt/.flex-photo-checkpoint").exists())

    def test_changed_source_cannot_discard_an_unknown_prior_dispatch(self):
        self.photo("a.heic", 0, unresolved=True)
        uncertain = Mock()
        uncertain.recognize.side_effect = CloudUnavailable("unknown_outcome")
        self.assertEqual(self.run_batch(uncertain).status, "incomplete")
        self.photo("a.heic", 0)
        revised = b"authored revised source while previous dispatch is unresolved"
        (self.source / "a.heic").write_bytes(revised)
        self.originals["a.heic"] = revised
        renewed = Mock()
        second = self.run_batch(renewed, resume=True)
        self.assertEqual(second.status, "incomplete")
        renewed.recognize.assert_not_called()
        self.assertEqual((self.source / "a.heic").read_bytes(), revised)
        self.assertTrue((self.output / ".flex-photo-gpt/.flex-photo-checkpoint").is_dir())
