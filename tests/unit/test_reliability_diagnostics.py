"""UTF-8 OCR and bounded opt-in stack diagnostics."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import flex_photo._interpretation_worker as worker
from flex_photo.diagnostics import Diagnostics, _LIMIT
from flex_photo.interpretation import InterpretationAssets, _diagnostic_trace, interpret_photo


class ReliabilityDiagnosticsTests(unittest.TestCase):
    def test_ocr_explicit_utf8_retains_unexpected_unicode_without_reader_failure(self):
        from PIL import Image
        assets = InterpretationAssets(Path("engine"), Path("models"), "0" * 64)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "models").mkdir()
            model = b"authored model"
            (folder / "models/eng.traineddata").write_bytes(model)
            with patch.object(worker, "_validate_assets"), \
                 patch.object(worker, "_MODEL_SHA256", hashlib.sha256(model).hexdigest()), \
                 patch.object(worker.subprocess, "run", return_value=subprocess.CompletedProcess(
                     "engine", 0, "\u201d")) as execute:
                result = worker._ocr(Image.new("RGB", (20, 20)), (0, 0, 20, 20), assets, folder)
            self.assertEqual(result, ("\u201d", "\u201d"))
            self.assertTrue(all(call.kwargs["encoding"] == "utf-8" for call in execute.call_args_list))
            self.assertIsNone(worker._parse_field("trip_duration", "Trip Time " + result[0]))

    def test_worker_guard_reason_and_trace_require_explicit_diagnostics(self):
        for enabled in (False, True):
            request = {"exe": "engine", "models": "models", "sha": "0" * 64,
                       "path": "photo.heic", "workspace": "unused", "diagnostics": enabled}
            output = io.StringIO()
            with ExitStack() as stack:
                if os.name != "nt":
                    stack.enter_context(patch("resource.setrlimit"))
                stack.enter_context(patch.object(worker.sys, "stdin", io.StringIO(json.dumps(request))))
                stack.enter_context(patch.object(worker, "_validate_assets", side_effect=ValueError(
                    "primary pixel limit exceeded")))
                with redirect_stdout(output):
                    worker.main()
            value = json.loads(output.getvalue())
            self.assertEqual(value["error"], "primary pixel limit exceeded")
            self.assertEqual("diagnostic_trace" in value, enabled)
            if enabled:
                self.assertIn("ValueError", value["diagnostic_trace"])
                self.assertNotIn("primary pixel limit exceeded", value["diagnostic_trace"])

    def test_parent_propagates_trace_only_on_opt_in(self):
        assets = InterpretationAssets(Path("engine"), Path("models"), "0" * 64)
        for enabled in (False, True):
            with patch("flex_photo.interpretation._validate_assets"), \
                 patch.object(worker, "run_bounded", return_value={
                     "error": "individual failure", "diagnostic_trace": "safe stack"}) as run:
                result = interpret_photo(Path("photo.heic"), assets, diagnostics=enabled)
            self.assertEqual(result.diagnostic_trace, "safe stack" if enabled else None)
            self.assertEqual(run.call_args.kwargs, {"diagnostics": True} if enabled else {})

    def test_stack_omits_exception_message_source_and_locals(self):
        try:
            raise ValueError("PRIVATE OCR VALUE")
        except ValueError as error:
            trace = _diagnostic_trace(error)
        self.assertIn("test_stack_omits_exception_message_source_and_locals", trace)
        self.assertIn("ValueError", trace)
        self.assertNotIn("PRIVATE OCR VALUE", trace)
        self.assertNotIn(str(Path(__file__).parent), trace)

    def test_sink_disabled_deduplicated_and_bounded_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Diagnostics(root).record("decode", "stack")
            self.assertEqual(list(root.iterdir()), [])
            sink = Diagnostics(root, True)
            sink.record("decode", "stack")
            path = root / ".flex-photo-diagnostic.log"
            first = path.read_bytes()
            sink.record("decode", "different stack")
            self.assertEqual(path.read_bytes(), first)
            for index in range(40):
                Diagnostics(root, True).record("decode", "frame\n" * 1500)
            files = list(root.iterdir())
            self.assertEqual(len(files), 2)
            self.assertTrue(all(file.stat().st_size <= _LIMIT for file in files))

    def test_sink_failure_is_nonfatal_and_warned_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".flex-photo-diagnostic.log").mkdir()
            sink = Diagnostics(root, True)
            output = io.StringIO()
            with redirect_stderr(output):
                sink.record("decode", "stack")
                sink.record("ocr", "stack")
            self.assertEqual(output.getvalue().count("diagnostic-failed:"), 1)


if __name__ == "__main__":
    unittest.main()
