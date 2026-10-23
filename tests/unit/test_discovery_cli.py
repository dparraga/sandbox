"""Discovery command errors must not leak source paths or partial inventory."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flex_photo.cli import main
from flex_photo.discovery import DiscoveryError


class DiscoveryCliTests(unittest.TestCase):
    def invoke(self, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                status = main(arguments)
            except SystemExit as error:
                status = error.code
        return status, output.getvalue(), errors.getvalue()

    def test_inventory_exact_ascii_json_and_newline(self):
        with patch("flex_photo.cli.discover_heic", return_value=(Path("a.heic"), Path("caf\u00e9.heic"))):
            self.assertEqual(self.invoke(["discover", "."]), (0, '["a.heic", "caf\\u00e9.heic"]\n', ""))

    def test_scan_failure_no_partial_output_or_private_os_text(self):
        error = DiscoveryError("scan-failed", Path("private\nsource"), PermissionError("private OS text"), reason="directory enumeration failed")
        with patch("flex_photo.cli.discover_heic", side_effect=error):
            status, output, errors = self.invoke(["discover", "."])
        self.assertEqual((status, output), (1, ""))
        self.assertEqual(errors, "scan-failed: directory enumeration failed\n")

    def test_enumeration_failure_after_candidate_never_prints_partial_json(self):
        import stat
        from types import SimpleNamespace
        entry = SimpleNamespace(name="a.heic", stat=lambda **kwargs: SimpleNamespace(st_mode=stat.S_IFREG))
        class Entries:
            def __enter__(self):
                return self.generate()
            def __exit__(self, *args):
                pass
            def generate(self):
                yield entry
                raise PermissionError("private OS text")
        with tempfile.TemporaryDirectory() as root, patch("flex_photo.discovery.os.scandir", return_value=Entries()):
            status, output, errors = self.invoke(["discover", root])
        self.assertEqual((status, output), (1, ""))
        self.assertEqual(errors, "scan-failed: directory enumeration failed\n")

    def test_discovery_requires_source_and_rejects_extra_arguments(self):
        for arguments in [["discover"], ["discover", ".", "extra"]]:
            with self.subTest(arguments=arguments):
                status, output, errors = self.invoke(arguments)
                self.assertEqual((status, output), (2, ""))
                self.assertIn("usage:", errors)

    def test_broken_output_is_clean_failure(self):
        class BrokenOutput(io.StringIO):
            def write(self, text):
                raise BrokenPipeError("private OS text")
        errors = io.StringIO()
        with patch("flex_photo.cli.discover_heic", return_value=()), contextlib.redirect_stdout(BrokenOutput()), contextlib.redirect_stderr(errors):
            status = main(["discover", "."])
        self.assertEqual(status, 1)
        self.assertEqual(errors.getvalue(), "output-failed: unable to write console output\n")


if __name__ == "__main__":
    unittest.main()
