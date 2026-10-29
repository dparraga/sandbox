"""Durable extraction reuse and safe checkpoint ownership."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flex_photo.checkpoint import Checkpoint


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="flex checkpoint \u00e9 ")
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name)
        self.config = {"roots": {"source": {"path": "authored", "identity": [1, 2]}},
                       "window_microseconds": 180_000_000, "recipe_version": 2,
                       "executable_sha256": "a" * 64}

    def create(self):
        return Checkpoint(self.output, self.config, candidates=["folder/a.heic", "b.HEIC"])

    def test_restart_restores_latest_results_without_rewriting_prior_work(self):
        checkpoint = self.create()
        manifest_before = (checkpoint.path / "manifest.json").read_bytes()
        checkpoint.append("folder/a.heic", "b" * 64,
                          {"layout": "trip_summary", "observations": [{"value": "0.0", "unit": "mi"}]},
                          {"active_seconds": 4., "processed_count": 1})
        first = (checkpoint.path / "results.jsonl").read_bytes()
        checkpoint.append("b.HEIC", "c" * 64, {"layout": "unresolved", "issues": ["decode failure"]},
                          {"active_seconds": 7., "processed_count": 2})
        self.assertTrue((checkpoint.path / "results.jsonl").read_bytes().startswith(first))
        self.assertEqual((checkpoint.path / "manifest.json").read_bytes(), manifest_before)
        resumed = Checkpoint(self.output, self.config, resume=True)
        self.assertEqual(len(resumed.results), 2)
        self.assertEqual(resumed.results["folder/a.heic"]["hash"], "b" * 64)
        self.assertEqual(resumed.timing["active_seconds"], 7.)

    def test_newer_manifest_timing_survives_restart_and_changed_input_replaces_result(self):
        checkpoint = self.create()
        checkpoint.append("b.HEIC", "a" * 64, {"layout": "unresolved"}, {"active_seconds": 4.})
        checkpoint.save({"active_seconds": 9.})
        resumed = Checkpoint(self.output, self.config, resume=True)
        self.assertEqual(resumed.timing, {"active_seconds": 9.})
        resumed.append("b.HEIC", "b" * 64, {"layout": "drive_info"}, {"active_seconds": 14.})
        again = Checkpoint(self.output, self.config, resume=True)
        self.assertEqual(again.results["b.HEIC"]["hash"], "b" * 64)
        self.assertEqual(again.timing["active_seconds"], 14.)
        self.assertEqual(len(again.history), 2)
        self.assertEqual([record["result"]["layout"] for record in again.history],
                         ["unresolved", "drive_info"])

    def test_only_torn_final_record_is_removed(self):
        checkpoint = self.create()
        checkpoint.append("b.HEIC", "a" * 64, {"layout": "nonmatch"}, {"active_seconds": 1.})
        journal = checkpoint.path / "results.jsonl"
        verified = journal.read_bytes()
        with journal.open("ab") as stream:
            stream.write(b'{"data":{"seq":2')
        restored = Checkpoint(self.output, self.config, resume=True)
        self.assertEqual(journal.read_bytes(), verified)
        self.assertEqual(len(restored.results), 1)
        with journal.open("ab") as stream:
            stream.write(b'{"corrupt":"complete"}\n')
        with self.assertRaisesRegex(ValueError, "corrupt completed"):
            Checkpoint(self.output, self.config, resume=True)

    def test_config_change_and_fresh_run_cannot_reuse_checkpoint(self):
        checkpoint = self.create()
        with self.assertRaisesRegex(ValueError, "use --resume"):
            self.create()
        changed = dict(self.config, recipe_version=3)
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            Checkpoint(self.output, changed, resume=True)
        self.assertTrue((checkpoint.path / "manifest.json").exists())

    def test_unexpected_file_blocks_cleanup_without_deleting_anything(self):
        checkpoint = self.create()
        unrelated = checkpoint.path / "private-note.txt"
        unrelated.write_text("preserve")
        with self.assertRaisesRegex(ValueError, "unexpected files"):
            checkpoint.finish()
        self.assertEqual(unrelated.read_text(), "preserve")
        self.assertTrue((checkpoint.path / "manifest.json").exists())
        unrelated.unlink()
        unrelated_output = self.output / "other.json"
        unrelated_output.write_text("preserve")
        checkpoint.finish()
        self.assertFalse(checkpoint.path.exists())
        self.assertEqual(unrelated_output.read_text(), "preserve")

    def test_hash_corruption_and_raw_evidence_are_rejected(self):
        checkpoint = self.create()
        with self.assertRaisesRegex(ValueError, "raw OCR"):
            checkpoint.append("b.HEIC", "a" * 64, {"observations": [{"raw_text": "private"}]}, {})
        with self.assertRaisesRegex(ValueError, "outside saved candidate"):
            checkpoint.append("other.heic", "a" * 64, {}, {})
        checkpoint.append("b.HEIC", "a" * 64, {"layout": "nonmatch"}, {})
        journal = checkpoint.path / "results.jsonl"
        envelope = json.loads(journal.read_bytes())
        envelope["data"]["result"]["layout"] = "unresolved"
        journal.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "corrupt completed"):
            Checkpoint(self.output, self.config, resume=True)

    def test_unsafe_paths_and_missing_resume_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "no extraction checkpoint"):
            Checkpoint(self.output, self.config, resume=True)
        for name in ("../a.heic", "/a.heic", "C:/a.heic", "folder\\a.heic", "./a.heic"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "path is invalid"):
                Checkpoint(self.output, self.config, candidates=[name])
        self.assertFalse((self.output / ".flex-photo-checkpoint").exists())

    def test_interrupted_cleanup_keeps_completion_distinct_from_active_work(self):
        checkpoint = self.create()
        checkpoint.append("b.HEIC", "a" * 64, {"layout": "nonmatch"}, {"active_seconds": 1.})
        original_unlink = Path.unlink
        def interrupt_manifest_deletion(path, *args, **kwargs):
            if path.parent.name == ".flex-photo-checkpoint-finished" and path.name == "manifest.json":
                raise SystemExit("authored process interruption during cleanup")
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", interrupt_manifest_deletion), self.assertRaises(SystemExit):
            checkpoint.finish()
        self.assertFalse(checkpoint.path.exists())
        finished = self.output / ".flex-photo-checkpoint-finished"
        self.assertTrue((finished / "manifest.json").exists())
        self.assertFalse((finished / "results.jsonl").exists())
        # Completion cannot be confused with an active checkpoint missing data.
        with self.assertRaisesRegex(ValueError, "no extraction checkpoint"):
            Checkpoint(self.output, self.config, resume=True)
        self.assertFalse(finished.exists())
        fresh = self.create()
        self.assertEqual(fresh.results, {})

    def test_finished_cleanup_preserves_unknown_files_before_new_processing(self):
        finished = self.output / ".flex-photo-checkpoint-finished"
        finished.mkdir()
        (finished / "unrelated.txt").write_text("preserve")
        with self.assertRaisesRegex(ValueError, "unexpected files"):
            self.create()
        self.assertEqual((finished / "unrelated.txt").read_text(), "preserve")
        self.assertFalse((self.output / ".flex-photo-checkpoint").exists())


if __name__ == "__main__":
    unittest.main()
