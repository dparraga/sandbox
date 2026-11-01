"""Offline cloud boundary checks; no credentials or inference requests."""

import unittest
from unittest.mock import Mock, patch

from flex_photo.cloud_access import CloudClient, CloudUnavailable, MODEL, parse_response


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


if __name__ == "__main__":
    unittest.main()
