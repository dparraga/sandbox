"""Read-only candidate selection and filesystem failure behavior."""

import builtins
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flex_photo.discovery import DiscoveryError, discover_heic


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def touch(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not an image")
        return path

    def test_selection_order_hidden_and_no_content_reads(self):
        wanted = ["z.HEIC", "a.heic", ".hidden/x.HeIc", "day 1/caf\u00e9.heic"]
        for name in wanted + ["other.heif", "other.heic.bak", "plain"]:
            self.touch(name)
        (self.root / "directory.heic").mkdir()
        (self.root / "empty.heic").touch()
        wanted.append("empty.heic")
        with patch.object(builtins, "open", side_effect=AssertionError("content opened")), patch.object(Path, "open", side_effect=AssertionError("content opened")):
            actual = discover_heic(self.root)
        self.assertEqual(actual, tuple(Path(name) for name in sorted(wanted)))

    def test_empty_directory(self):
        self.assertEqual(discover_heic(self.root), ())

    def test_invalid_missing_and_file_roots(self):
        for root in [self.root / "missing", self.touch("file.heic")]:
            with self.subTest(root=root.name), self.assertRaises(DiscoveryError) as caught:
                discover_heic(root)
            self.assertEqual(caught.exception.category, "invalid-source")

    def test_hardlinked_names_remain_distinct(self):
        original = self.touch("a.heic")
        try:
            os.link(original, self.root / "b.heic")
        except OSError as error:
            self.skipTest(f"Hardlinks unavailable: {error.__class__.__name__}")
        self.assertEqual(discover_heic(self.root), (Path("a.heic"), Path("b.heic")))

    def test_symlink_root_and_children_and_linked_ancestor(self):
        target = self.root / "target"
        target.mkdir()
        (target / "a.heic").touch()
        link = self.root / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
            (target / "file.heic").symlink_to(target / "a.heic")
            (target / "loop").symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error.__class__.__name__}")
        with self.assertRaises(DiscoveryError) as caught:
            discover_heic(link)
        self.assertEqual(caught.exception.category, "invalid-source")
        self.assertEqual(discover_heic(self.root), (Path("target/a.heic"),))
        (target / "ordinary").mkdir()
        (target / "ordinary/b.heic").touch()
        self.assertEqual(discover_heic(link / "ordinary"), (Path("b.heic"),))

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_windows_junction_root_rejected_and_subtree_skipped(self):
        target = self.root / "target"
        target.mkdir()
        (target / "a.heic").touch()
        link = self.root / "junction"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, "Could not create test junction")
        self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)
        with self.assertRaises(DiscoveryError) as caught:
            discover_heic(link)
        self.assertEqual(caught.exception.category, "invalid-source")
        self.assertEqual(discover_heic(self.root), (Path("target/a.heic"),))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX special-file behavior")
    def test_fifo_is_not_candidate(self):
        os.mkfifo(self.root / "pipe.heic")
        self.assertEqual(discover_heic(self.root), ())

    def test_root_stat_failure_wrapped(self):
        with patch.object(Path, "lstat", side_effect=PermissionError("private OS text")):
            with self.assertRaises(DiscoveryError) as caught:
                discover_heic(self.root)
        self.assertEqual(caught.exception.category, "invalid-source")

    def test_scandir_open_failure_wrapped(self):
        with patch("flex_photo.discovery.os.scandir", side_effect=PermissionError("private OS text")):
            with self.assertRaises(DiscoveryError) as caught:
                discover_heic(self.root)
        self.assertEqual(caught.exception.category, "scan-failed")

    def test_iterator_failure_wrapped_and_closed(self):
        class BrokenIterator:
            closed = False
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.closed = True
            def __iter__(self):
                return self
            def __next__(self):
                raise PermissionError("private OS text")
        iterator = BrokenIterator()
        with patch("flex_photo.discovery.os.scandir", return_value=iterator):
            with self.assertRaises(DiscoveryError) as caught:
                discover_heic(self.root)
        self.assertEqual(caught.exception.category, "scan-failed")
        self.assertTrue(iterator.closed)

    def test_entry_metadata_failure_wrapped(self):
        entry = SimpleNamespace(name="x.heic", path=str(self.root / "x.heic"))
        def failing_stat(*args, **kwargs):
            raise FileNotFoundError("private OS text")
        entry.stat = failing_stat
        class Entries:
            def __enter__(self):
                return iter([entry])
            def __exit__(self, *args):
                pass
        with patch("flex_photo.discovery.os.scandir", return_value=Entries()):
            with self.assertRaises(DiscoveryError) as caught:
                discover_heic(self.root)
        self.assertEqual(caught.exception.category, "scan-failed")

    def test_directory_handle_close_failure_rejects_completed_inventory(self):
        entry = SimpleNamespace(
            name="a.heic",
            stat=lambda **kwargs: SimpleNamespace(st_mode=stat.S_IFREG),
        )
        class Entries:
            def __enter__(self):
                return iter([entry])
            def __exit__(self, *args):
                raise OSError("private OS text")
        with patch("flex_photo.discovery.os.scandir", return_value=Entries()):
            with self.assertRaises(DiscoveryError) as caught:
                discover_heic(self.root)
        self.assertEqual(caught.exception.category, "scan-failed")
        self.assertEqual(caught.exception.reason, "directory enumeration failed")

    def test_windows_reparse_attribute_exclusion_without_cloud_dependency(self):
        original = Path.lstat
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        def attributes(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=reparse)
        with patch.object(Path, "lstat", attributes):
            with self.assertRaises(DiscoveryError) as caught:
                discover_heic(self.root)
        self.assertEqual(caught.exception.category, "invalid-source")

    def test_child_reparse_entries_are_skipped_without_enumerating_them(self):
        def metadata(**kwargs):
            self.assertEqual(kwargs, {"follow_symlinks": False})
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        entry = SimpleNamespace(name="cloud.heic", stat=metadata)
        file_entry = SimpleNamespace(name="downloaded.heic", stat=lambda **kwargs: SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT))
        class Entries:
            def __enter__(self):
                return iter([entry, file_entry])
            def __exit__(self, *args):
                pass
        with patch("flex_photo.discovery.os.scandir", return_value=Entries()) as scan:
            self.assertEqual(discover_heic(self.root), ())
        self.assertEqual(scan.call_count, 1)

    def test_queued_directory_disappearance_or_type_change_fails(self):
        child = self.root / "child"
        child.mkdir()
        real_stat = Path.lstat
        for replacement in [FileNotFoundError("gone"), SimpleNamespace(st_mode=stat.S_IFREG), SimpleNamespace(st_mode=stat.S_IFLNK), SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)]:
            def changed(path, *args, **kwargs):
                if path == child:
                    if isinstance(replacement, OSError):
                        raise replacement
                    return replacement
                return real_stat(path, *args, **kwargs)
            with self.subTest(replacement=type(replacement).__name__), patch.object(Path, "lstat", changed):
                with self.assertRaises(DiscoveryError) as caught:
                    discover_heic(self.root)
            self.assertEqual(caught.exception.category, "scan-failed")


if __name__ == "__main__":
    unittest.main()
