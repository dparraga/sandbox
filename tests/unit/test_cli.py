"""Behavior of the discovery and offline processing command interface."""

import contextlib
from datetime import timedelta
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from flex_photo import __version__
from flex_photo.cli import main


class CliTests(unittest.TestCase):
    def invoke(self, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                status = main(arguments)
            except SystemExit as error:
                status = error.code
        return status, output.getvalue(), errors.getvalue()

    def test_default_is_honest_readiness_message(self):
        status, output, errors = self.invoke([])
        self.assertEqual(status, 0)
        self.assertIn("photo processing", output.lower())
        self.assertIn("process --help", output)
        self.assertEqual(errors, "")

    def test_help_exits_successfully_and_describes_available_options(self):
        status, output, errors = self.invoke(["--help"])
        self.assertEqual(status, 0)
        self.assertIn("--version", output)
        self.assertIn("process", output)
        self.assertIn("discover", output)
        self.assertEqual(errors, "")

    def test_version_matches_package(self):
        status, output, errors = self.invoke(["--version"])
        self.assertEqual(status, 0)
        self.assertEqual(output.strip(), f"flex-photo {__version__}")
        self.assertEqual(errors, "")

    def test_unknown_option_is_an_argument_error(self):
        status, output, errors = self.invoke(["--not-a-real-option"])
        self.assertEqual(status, 2)
        self.assertEqual(output, "")
        self.assertIn("unrecognized arguments", errors)

    def test_auth_login_and_status_do_not_confirm_billing_implicitly(self):
        for action in ("login", "status"):
            with self.subTest(action=action), patch("flex_photo.subscription_auth.CredentialStore") as store, \
                    patch("flex_photo.subscription_auth.sign_in") as login, \
                    patch("flex_photo.subscription_auth.confirm_subscription_only") as confirm, \
                    patch("flex_photo.subscription_auth.auth_status", return_value={
                        "connected": True, "plan_usage_granted": True, "subscription_only_verified": False}):
                status, output, errors = self.invoke(["auth", action])
                self.assertEqual(status, 0)
                self.assertFalse(json.loads(output)["subscription_only_verified"])
                self.assertIsNone(json.loads(output)["subscription_only_verification_source"])
                self.assertEqual(login.call_count, int(action == "login"))
                confirm.assert_not_called()
                if action == "status":
                    self.assertEqual(errors, "")

    def test_auth_confirmation_records_user_verification_without_signing_in_again(self):
        with patch("flex_photo.subscription_auth.CredentialStore") as store, \
                patch("flex_photo.subscription_auth.sign_in") as login, \
                patch("flex_photo.subscription_auth.confirm_subscription_only") as confirm, \
                patch("flex_photo.subscription_auth.auth_status", return_value={
                    "connected": True, "plan_usage_granted": True, "subscription_only_verified": True}):
            status, output, errors = self.invoke(["auth", "confirm-subscription-only"])
        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        confirm.assert_called_once_with(store.return_value)
        login.assert_not_called()
        self.assertEqual(json.loads(output)["subscription_only_verification_source"],
                         "user-verified-provider-configuration")

    def test_auth_cancellation_and_failure_are_sanitized(self):
        for error, expected in ((KeyboardInterrupt(), 130), (ValueError("private token text"), 1)):
            with self.subTest(error=type(error).__name__), \
                    patch("flex_photo.subscription_auth.CredentialStore"), \
                    patch("flex_photo.subscription_auth.sign_in", side_effect=error):
                status, output, errors = self.invoke(["auth", "login"])
                self.assertEqual(status, expected)
                self.assertEqual(output, "")
                self.assertNotIn("private token text", errors)

    def test_process_forwards_explicit_assets_window_and_result_status(self):
        from flex_photo.batch import BatchResult
        from flex_photo.interpretation import InterpretationAssets
        arguments = ["process", "source", "--destination", "destination", "--json-output", "output",
                     "--tesseract", "engine", "--tessdata", "models", "--tesseract-sha256", "a" * 64]
        for state, expected in (("complete", 0), ("incomplete", 1), ("paused", 0)):
            with self.subTest(state=state), patch("flex_photo.batch.process_batch",
                    return_value=BatchResult(state, Path("report.json"), {"trips": 1})) as process:
                status, output, errors = self.invoke(arguments + ["--window-seconds", "12.5", "--resume", "--diagnostics"])
                self.assertEqual(status, expected)
                self.assertEqual(json.loads(output)["status"], state)
                self.assertEqual(errors, "")
                process.assert_called_once_with(Path("source"), Path("destination"), Path("output"),
                    assets=InterpretationAssets(Path("engine"), Path("models"), "a" * 64),
                    window=timedelta(seconds=12.5), resume=True, diagnostics=True, display_progress=True,
                    gpt_fallback=False)

    def test_invalid_processing_windows_are_argument_errors_before_processing(self):
        arguments = ["process", "source", "--destination", "destination", "--json-output", "output",
                     "--tesseract", "engine", "--tessdata", "models", "--tesseract-sha256", "a" * 64]
        for value in ("-1", "nan", "inf", "1e300"):
            with self.subTest(value=value), patch("flex_photo.batch.process_batch") as process:
                status, output, errors = self.invoke(arguments + ["--window-seconds", value])
                self.assertEqual(status, 2)
                self.assertEqual(output, "")
                self.assertIn("--window-seconds", errors)
                process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
