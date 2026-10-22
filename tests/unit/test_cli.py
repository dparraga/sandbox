"""Behavior of the intentionally small bootstrap CLI."""

import contextlib
import io
import unittest

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
        self.assertIn("bootstrap", output.lower())
        self.assertIn("photo processing", output.lower())
        self.assertIn("unavailable", output.lower())
        self.assertEqual(errors, "")

    def test_help_exits_successfully_and_describes_available_options(self):
        status, output, errors = self.invoke(["--help"])
        self.assertEqual(status, 0)
        self.assertIn("--version", output)
        self.assertIn("bootstrap", output.lower())
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


if __name__ == "__main__":
    unittest.main()
