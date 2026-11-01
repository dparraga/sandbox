"""Offline cloud boundary checks; no credentials or inference requests."""

import unittest
import io
import json
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

from flex_photo.cloud_access import (
    CloudClient, CloudUnavailable, InvalidResponse, KnownRequestRejected, MODEL,
    SubscriptionTransport, parse_response,
)


class CloudAccessTests(unittest.TestCase):
    def request(self):
        return {"model": MODEL, "store": False, "stream": True,
                "instructions": "Return only the requested readings.", "input": []}

    def test_default_blocks_before_network_environment_or_credential_reads(self):
        with patch("builtins.open", side_effect=AssertionError("file read")), \
                patch("os.getenv", side_effect=AssertionError("environment read")), \
                patch("socket.create_connection", side_effect=AssertionError("network")):
            for call in (CloudClient().check_available,
                         lambda: CloudClient().recognize(self.request())):
                with self.assertRaises(CloudUnavailable) as caught:
                    call()
                self.assertEqual(caught.exception.category, "included_only_unverified")

    def test_injected_completed_result_preserves_request_and_strict_output(self):
        transport = Mock()
        transport.recognize.return_value = '{"reading":{"value":"17.0","unit":"mi"}}'
        request = self.request()
        result = CloudClient(transport).recognize(request)
        self.assertEqual(result, {"reading": {"value": "17.0", "unit": "mi"}})
        transport.check_available.assert_called_once_with()
        transport.recognize.assert_called_once_with(request)

    def test_exact_model_and_supported_streaming_requirements(self):
        for key, value in (("model", "gpt-6-astra"), ("model", None),
                           ("store", True), ("stream", False), ("input", "text")):
            with self.subTest(key=key, value=value):
                transport = Mock()
                request = self.request()
                request[key] = value
                with self.assertRaises(CloudUnavailable):
                    CloudClient(transport).recognize(request)
                transport.recognize.assert_not_called()

    def test_availability_failures_stop_dispatch_and_do_not_expose_transport_text(self):
        transport = Mock()
        transport.check_available.side_effect = RuntimeError("secret/image-path")
        with self.assertRaises(CloudUnavailable) as caught:
            CloudClient(transport).recognize(self.request())
        self.assertEqual(str(caught.exception), "unavailable")
        self.assertIsInstance(caught.exception, KnownRequestRejected)
        self.assertIsNone(caught.exception.__cause__)
        transport.recognize.assert_not_called()

    def test_known_failures_keep_category_and_never_retry(self):
        for category in ("authentication", "network", "quota", "model", "unavailable"):
            with self.subTest(category=category):
                transport = Mock()
                transport.recognize.side_effect = CloudUnavailable(category)
                with self.assertRaises(CloudUnavailable) as caught:
                    CloudClient(transport).recognize(self.request())
                self.assertEqual(caught.exception.category, category)
                transport.recognize.assert_called_once()

    def test_dispatch_failure_is_unknown_without_retry_or_private_exception_text(self):
        transport = Mock()
        transport.recognize.side_effect = TimeoutError("private image content")
        with self.assertRaises(CloudUnavailable) as caught:
            CloudClient(transport).recognize(self.request())
        self.assertEqual(str(caught.exception), "unknown_outcome")
        transport.recognize.assert_called_once()

    def test_strict_model_json(self):
        for raw in ('{"x":1,"x":2}', '{"x":{"a":1,"a":2}}',
                    '{"x":NaN}', '{"x":Infinity}', '{"x":{"y":1e999}}',
                    '[]', 'null',
                    '```json\n{}\n```', '{', {"x": float("inf")}, {"x": object()}):
            with self.subTest(raw=raw):
                with self.assertRaises(CloudUnavailable) as caught:
                    parse_response(raw)
                self.assertEqual(caught.exception.category, "invalid_response")

    def test_unknown_category_cannot_leak_into_reports(self):
        with self.assertRaises(ValueError):
            CloudUnavailable("secret/image-path")

    def test_invalid_response_detail_is_bounded_and_contains_no_provider_text(self):
        for raw, expected in (('private provider prose', "json"), ('[]', "unexpected_shape")):
            with self.subTest(expected=expected), self.assertRaises(InvalidResponse) as caught:
                parse_response(raw)
            self.assertEqual(caught.exception.detail, expected)
            self.assertEqual(caught.exception.category, "invalid_response")
            self.assertEqual(str(caught.exception), "invalid_response")
            self.assertIsNone(caught.exception.__cause__)
        with self.assertRaises(ValueError):
            InvalidResponse("private provider prose")


class SubscriptionTransportTests(unittest.TestCase):
    def request(self):
        return {"model": MODEL, "store": False, "stream": True, "input": []}

    def text_event(self, kind, text):
        return ("data: " + json.dumps({"type": kind, "output_index": 0, "content_index": 0,
                                      "text" if kind.endswith(".done") else "delta": text}) + "\n\n").encode()

    def event(self, kind="response.completed", **response):
        result = {"model": MODEL, "status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": '{"value":"17.0"}'}]}]}
        result.update(response)
        return ("data: " + json.dumps({"type": kind, "response": result}) + "\n\n").encode()

    def transport(self, response, *, catalog=None):
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(json.dumps(catalog or {
            "models": [{"slug": MODEL}]}).encode()), io.BytesIO(response)]
        return SubscriptionTransport(Mock(), billing_guard=Mock(), opener=opener), opener

    def test_default_gate_blocks_before_tokens_or_http(self):
        opener = Mock()
        with patch("flex_photo.subscription_auth.access_token") as token, \
                patch("flex_photo.subscription_auth.SubscriptionOnlyGuard.check_available",
                      side_effect=CloudUnavailable("included_only_unverified")):
            with self.assertRaises(CloudUnavailable) as caught:
                SubscriptionTransport(Mock(), opener=opener).recognize(self.request())
            self.assertEqual(caught.exception.category, "included_only_unverified")
            token.assert_not_called()
            opener.open.assert_not_called()

    @patch("flex_photo.subscription_auth.access_token", return_value="app-owned-token")
    def test_completed_only_exact_endpoint_model_and_bearer(self, _):
        transport, opener = self.transport(self.event())
        self.assertEqual(CloudClient(transport).recognize(self.request()), {"value": "17.0"})
        requests = [call.args[0] for call in opener.open.call_args_list]
        self.assertEqual([item.full_url for item in requests], [
            "https://api.openai.com/v1/models", "https://api.openai.com/v1/responses"])
        self.assertEqual(requests[1].get_header("Authorization"), "Bearer app-owned-token")
        self.assertEqual(json.loads(requests[1].data)["model"], MODEL)

    @patch("flex_photo.subscription_auth.access_token", return_value="app-owned-token")
    def test_exact_luna_missing_catalog_does_not_substitute(self, _):
        transport, opener = self.transport(self.event(), catalog={"models": [{"slug": "gpt-6-astra"}]})
        with self.assertRaises(CloudUnavailable) as caught:
            transport.recognize(self.request())
        self.assertEqual(caught.exception.category, "model")
        self.assertEqual(opener.open.call_count, 1)

    @patch("flex_photo.subscription_auth.access_token", return_value="app-owned-token")
    def test_only_explicit_subscription_quota_is_quota(self, _):
        for code, expected in (("subscription_sharing_usage_limit_exceeded", "quota"),
                               ("subscription_sharing_usage_unavailable", "unavailable"),
                               ("rate_limit_exceeded", "unavailable")):
            with self.subTest(code=code):
                transport, opener = self.transport(self.event("response.failed", error={"code": code}))
                with self.assertRaises(CloudUnavailable) as caught:
                    transport.recognize(self.request())
                self.assertEqual(caught.exception.category, expected)
                self.assertEqual(opener.open.call_count, 2)

    @patch("flex_photo.subscription_auth.access_token", return_value="app-owned-token")
    def test_partial_malformed_and_oversized_streams_have_unknown_outcome(self, _):
        for body in (b"", b'data: {bad}\n\n', b'data: ' + b'x' * 65537,
                     b'data: {"type":"response.output_text.delta","delta":"17.0"}\n\n'):
            with self.subTest(body_length=len(body)):
                transport, _ = self.transport(body)
                with self.assertRaises(CloudUnavailable) as caught:
                    transport.recognize(self.request())
                self.assertEqual(caught.exception.category, "unknown_outcome")

    @patch("flex_photo.subscription_auth.access_token", return_value="app-owned-token")
    def test_http_quota_auth_generic429_and_dispatch_timeout_are_distinct(self, _):
        for status, code, expected in ((429, "subscription_sharing_usage_limit_exceeded", "quota"),
                                       (429, "rate_limit_exceeded", "unavailable"),
                                       (401, "invalid_token", "authentication")):
            transport, opener = self.transport(b"")
            error = HTTPError("https://api.openai.com/v1/responses", status, "private", {},
                              io.BytesIO(json.dumps({"error": {"code": code}}).encode()))
            opener.open.side_effect = [io.BytesIO(b'{"models":[{"slug":"gpt-6-luna"}]}'), error]
            with self.assertRaises(CloudUnavailable) as caught:
                transport.recognize(self.request())
            self.assertEqual(caught.exception.category, expected)
            if expected != "quota":
                self.assertIsInstance(caught.exception, KnownRequestRejected)
            self.assertEqual(opener.open.call_count, 2)
        transport, opener = self.transport(b"")
        opener.open.side_effect = [io.BytesIO(b'{"models":[{"slug":"gpt-6-luna"}]}'), URLError("private")]
        with self.assertRaises(CloudUnavailable) as caught:
            transport.recognize(self.request())
        self.assertEqual(caught.exception.category, "unknown_outcome")
        self.assertNotIsInstance(caught.exception, KnownRequestRejected)

    def test_redirect_handler_never_forwards_authorization(self):
        from flex_photo.cloud_access import _NoRedirect
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid"))

    @patch("flex_photo.subscription_auth.access_token", side_effect=CloudUnavailable("authentication"))
    def test_expired_auth_before_post_is_known_not_unknown(self, _):
        transport, opener = self.transport(self.event())
        transport._catalog_checked = True
        with self.assertRaises(KnownRequestRejected) as caught:
            transport.recognize(self.request())
        self.assertEqual(caught.exception.category, "authentication")
        opener.open.assert_not_called()

    @patch("flex_photo.subscription_auth.access_token", return_value="app-owned-token")
    def test_completed_invalid_output_and_incomplete_have_safe_details(self, _):
        for kind, fields, expected in (
                ("response.incomplete", {}, "incomplete"),
                ("response.completed", {"status": "in_progress"}, "noncompleted_status"),
                ("response.completed", {"output": None}, "unexpected_shape"),
                ("response.completed", {"output": []}, "empty_output")):
            with self.subTest(expected=expected):
                transport, _ = self.transport(self.event(kind, **fields))
                with self.assertRaises(InvalidResponse) as caught:
                    transport.recognize(self.request())
                self.assertEqual(caught.exception.detail, expected)
                self.assertNotIsInstance(caught.exception, KnownRequestRejected)

    @patch("flex_photo.subscription_auth.access_token", return_value="app-owned-token")
    def test_metadata_only_completed_uses_delta_or_done_text_once(self, _):
        value = '{"value":"17.0"}'
        delta = self.text_event("response.output_text.delta", value)
        done = self.text_event("response.output_text.done", value)
        for text_events in (delta, done, delta + done):
            with self.subTest(events=len(text_events)):
                transport, _ = self.transport(text_events + self.event(output=[]))
                self.assertEqual(CloudClient(transport).recognize(self.request()), {"value": "17.0"})
        transport, _ = self.transport(delta + done + self.event())
        self.assertEqual(transport.recognize(self.request()), value)

    @patch("flex_photo.subscription_auth.access_token", return_value="app-owned-token")
    def test_text_done_without_completion_remains_unknown(self, _):
        transport, _ = self.transport(self.text_event("response.output_text.done", '{"value":"17.0"}'))
        with self.assertRaises(CloudUnavailable) as caught:
            transport.recognize(self.request())
        self.assertEqual(caught.exception.category, "unknown_outcome")

    @patch("flex_photo.subscription_auth.access_token", return_value="app-owned-token")
    def test_streamed_text_never_bypasses_refusal_tool_or_conflicting_final_text(self, _):
        value = '{"value":"17.0"}'
        delta = self.text_event("response.output_text.delta", value)
        for extra, terminal, expected in (
                (b'data: {"type":"response.refusal.done","refusal":"private"}\n\n', self.event(), "refusal"),
                (b'data: {"type":"response.output_item.done","item":{"type":"function_call"}}\n\n',
                 self.event(), "unexpected_output"),
                (self.text_event("response.output_text.done", '{"value":"99"}'), self.event(output=[]), "unexpected_shape"),
                (b"", self.event(output=[{"type": "message", "content": [
                    {"type": "output_text", "text": '{"value":"99"}'}]}]), "unexpected_shape")):
            with self.subTest(expected=expected):
                transport, _ = self.transport(delta + extra + terminal)
                with self.assertRaises(InvalidResponse) as caught:
                    transport.recognize(self.request())
                self.assertEqual(caught.exception.detail, expected)


if __name__ == "__main__":
    unittest.main()
