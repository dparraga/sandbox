"""Exercise installed artifacts outside the checkout, without private photos."""

import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import unittest
import zipfile
from email.parser import BytesParser

from flex_photo import __version__


class InstalledCliTests(unittest.TestCase):
    def test_wheel_metadata_and_payload(self):
        wheel = Path(os.environ["FLEX_PHOTO_WHEEL"]).resolve(strict=True)
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
            self.assertEqual(len(metadata_names), 1)
            metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
            self.assertEqual(metadata["Name"], "flex-photo")
            self.assertEqual(metadata["Version"], __version__)
            self.assertEqual(metadata["License-Expression"], "MIT")
            self.assertEqual(metadata["Requires-Python"], "<3.15,>=3.13")
            self.assertEqual(metadata.get_all("Requires-Dist"), ["ExifRead==3.5.1"])
            license_names = [name for name in names if name.endswith(".dist-info/licenses/LICENSE")]
            self.assertEqual(len(license_names), 1)
            app_license = archive.read(license_names[0]).decode("utf-8")
            self.assertEqual(app_license.splitlines()[0], "MIT License")
            self.assertIn("Copyright (c) 2024-2026 Daniel P\u00e1rraga", app_license)
            self.assertIn("The above copyright notice and this permission notice", app_license)
            self.assertEqual(
                {name for name in names if not name.split("/")[0].endswith(".dist-info")},
                {"flex_photo/__init__.py", "flex_photo/__main__.py", "flex_photo/cli.py", "flex_photo/discovery.py", "flex_photo/metadata.py", "flex_photo/capture_time.py", "flex_photo/grouping.py", "flex_photo/selection.py"},
            )
        installed = importlib.metadata.distribution("flex-photo")
        self.assertEqual(installed.version, __version__)
        self.assertEqual(installed.requires, ["ExifRead==3.5.1"])
        backend = importlib.metadata.distribution("ExifRead")
        self.assertEqual(backend.version, "3.5.1")
        # The pinned wheel has development/test extras, not runtime dependencies.
        self.assertTrue(all('; extra == "dev"' in item or '; extra == "test"' in item
                            for item in backend.requires or []))
        licenses = [path for path in backend.files if str(path).endswith(".dist-info/licenses/LICENSE")]
        self.assertEqual(len(licenses), 1)
        notice = backend.locate_file(licenses[0]).read_text(encoding="utf-8")
        self.assertIn("Redistribution and use in source and binary forms", notice)
        self.assertIn("THIS SOFTWARE IS PROVIDED", notice)
        entry = [entry for entry in installed.entry_points if entry.group == "console_scripts"]
        self.assertEqual([(item.name, item.value) for item in entry], [("flex-photo", "flex_photo.cli:main")])

    def test_module_and_console_outside_checkout(self):
        scripts = Path(sysconfig.get_path("scripts"))
        console = scripts / ("flex-photo.exe" if os.name == "nt" else "flex-photo")
        self.assertTrue(console.is_file(), str(console))
        commands = [[sys.executable, "-m", "flex_photo"], [str(console)]]
        with tempfile.TemporaryDirectory(prefix="flex bootstrap é ") as directory:
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            environment["PYTHONNOUSERSITE"] = "1"
            # An installed wheel must resolve from this interpreter's environment,
            # rather than a source checkout or an editable-install link.
            probe = subprocess.run(
                [sys.executable, "-c", "from pathlib import Path; import flex_photo,sys; "
                 "assert Path(flex_photo.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())"],
                cwd=directory, env=environment, capture_output=True, text=True, timeout=15, check=False,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            for command in commands:
                for arguments, expected in [([], 0), (["--help"], 0), (["--version"], 0), (["--invalid-option"], 2)]:
                    with self.subTest(command=command, arguments=arguments):
                        result = subprocess.run(command + arguments, cwd=directory, env=environment,
                                                capture_output=True, text=True, timeout=15, check=False)
                        self.assertEqual(result.returncode, expected, result.stderr)
                        if expected == 2:
                            self.assertEqual(result.stdout, "")
                            self.assertIn("unrecognized arguments", result.stderr)
                        else:
                            self.assertEqual(result.stderr, "")
                            if arguments == ["--version"]:
                                self.assertEqual(result.stdout.strip(), f"flex-photo {__version__}")
                            elif arguments == ["--help"]:
                                self.assertIn("--version", result.stdout)
                            else:
                                self.assertIn("bootstrap", result.stdout.lower())
                                self.assertIn("unavailable", result.stdout.lower())
                        self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
