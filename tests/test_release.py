"""Offline behavioral checks for the source-release boundary."""

import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_release.py"
SPEC = importlib.util.spec_from_file_location("build_release", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="release-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.root = self.directory / "source"
        self.root.mkdir()
        self.output = self.directory / "output" / "source.zip"
        self.write("README.md", "Public introduction / 项目说明\n")
        self.write("src/example.py", "print('public')\n")
        self.manifest("src/example.py", "README.md", "release-files.txt")

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def manifest(self, *names):
        return self.write("release-files.txt", "\n".join(names) + "\n")

    def link(self, source, destination, is_directory=False):
        try:
            destination.symlink_to(source, target_is_directory=is_directory)
        except (NotImplementedError, OSError) as error:
            self.skipTest("OS does not permit creating symlinks: %s" % error)

    def test_only_explicit_sources_are_included(self):
        for name in (".env", ".claude/codex-collaborate.json", ".codex/settings.json",
                     "session.jsonl", "__pycache__/example.pyc", "private-notes.txt"):
            self.write(name, "PRIVATE_MARKER_DO_NOT_PACKAGE")
        names = release.build_release(self.root, self.output)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.namelist(), ["README.md", "release-files.txt", "src/example.py"])
            self.assertEqual(archive.namelist(), names)
            self.assertTrue(all(b"PRIVATE_MARKER" not in archive.read(name) for name in names))

    def test_explicit_private_and_cache_entries_are_rejected(self):
        for name in (".env", ".env.local", ".claude/session.json", ".codex/settings.json",
                     ".aws/config", "src/__pycache__/x.pyc", "events.jsonl", "debug.log"):
            with self.subTest(name=name):
                self.write(name, "private")
                self.manifest(name)
                with self.assertRaises(release.ReleaseError):
                    release.build_release(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_traversal_and_nonportable_manifest_paths_are_rejected(self):
        for name in ("../outside.txt", "/etc/passwd", "C:/private.txt", "src\\example.py",
                     "src/../../outside.txt", "./README.md", "src//example.py", "src/CON.txt"):
            with self.subTest(name=name):
                self.manifest(name)
                with self.assertRaises(release.ReleaseError):
                    release.build_release(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_duplicate_and_case_colliding_entries_are_rejected(self):
        for names in (("README.md", "README.md"), ("README.md", "readme.md")):
            with self.subTest(names=names):
                self.manifest(*names)
                with self.assertRaises(release.ReleaseError):
                    release.build_release(self.root, self.output)

    def test_missing_or_nonregular_input_preserves_existing_output(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"existing-output")
        for name in ("missing.md", "src"):
            with self.subTest(name=name):
                self.manifest("README.md", name)
                with self.assertRaises(release.ReleaseError):
                    release.build_release(self.root, self.output)
                self.assertEqual(self.output.read_bytes(), b"existing-output")

    def test_source_symlink_is_rejected(self):
        outside = self.directory / "private.txt"
        outside.write_text("private", encoding="utf-8")
        self.link(outside, self.root / "linked.md")
        self.manifest("linked.md")
        with self.assertRaisesRegex(release.ReleaseError, "Symlinks"):
            release.build_release(self.root, self.output)

    def test_parent_directory_symlink_is_rejected(self):
        outside = self.directory / "private"
        outside.mkdir()
        (outside / "file.md").write_text("private", encoding="utf-8")
        self.link(outside, self.root / "linked", is_directory=True)
        self.manifest("linked/file.md")
        with self.assertRaisesRegex(release.ReleaseError, "Symlinks"):
            release.build_release(self.root, self.output)

    def test_manifest_symlink_is_rejected(self):
        alternate = self.directory / "manifest.txt"
        alternate.write_text("README.md\n", encoding="utf-8")
        (self.root / "release-files.txt").unlink()
        self.link(alternate, self.root / "release-files.txt")
        with self.assertRaisesRegex(release.ReleaseError, "Symlinks"):
            release.build_release(self.root, self.output)

    def test_output_symlink_is_rejected(self):
        outside = self.directory / "untouched.txt"
        outside.write_bytes(b"untouched")
        self.output.parent.mkdir()
        self.link(outside, self.output)
        with self.assertRaisesRegex(release.ReleaseError, "Symlinks"):
            release.build_release(self.root, self.output)
        self.assertEqual(outside.read_bytes(), b"untouched")

    def test_output_cannot_overwrite_source(self):
        original = (self.root / "README.md").read_bytes()
        with self.assertRaisesRegex(release.ReleaseError, "overwrite"):
            release.build_release(self.root, self.root / "README.md")
        self.assertEqual((self.root / "README.md").read_bytes(), original)

    def test_reparse_points_without_symlink_mode_are_rejected(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"existing-output")
        original_lstat = Path.lstat
        for target in (self.root, self.root / "src", self.root / "src/example.py",
                       self.output.parent, self.output):
            with self.subTest(target=target):
                def reparse_lstat(path, *args, **kwargs):
                    details = original_lstat(path, *args, **kwargs)
                    if path == target:
                        # Model Windows junctions/reparse files that retain a
                        # normal directory/file mode on Python 3.9.
                        self.assertFalse(stat.S_ISLNK(details.st_mode))
                        return SimpleNamespace(
                            st_mode=details.st_mode,
                            st_dev=details.st_dev,
                            st_ino=details.st_ino,
                            st_file_attributes=release.REPARSE_POINT,
                        )
                    return details

                with mock.patch.object(Path, "lstat", reparse_lstat):
                    with self.assertRaisesRegex(release.ReleaseError, "reparse point"):
                        release.build_release(self.root, self.output)
                self.assertEqual(self.output.read_bytes(), b"existing-output")

    @unittest.skipUnless(os.name == "nt", "Native junction creation requires Windows")
    def test_native_windows_junction_is_rejected(self):
        outside = self.directory / "outside"
        outside.mkdir()
        (outside / "file.md").write_text("private", encoding="utf-8")
        junction = self.root / "junction"
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode:
            self.skipTest("This Windows environment cannot create directory junctions")
        try:
            self.assertTrue(junction.lstat().st_file_attributes & release.REPARSE_POINT)
            self.manifest("junction/file.md")
            with self.assertRaisesRegex(release.ReleaseError, "reparse point"):
                release.build_release(self.root, self.output)
            with self.assertRaisesRegex(release.ReleaseError, "reparse point"):
                release.build_release(junction, self.output)
            self.manifest("README.md")
            with self.assertRaisesRegex(release.ReleaseError, "reparse point"):
                release.build_release(self.root, junction / "source.zip")
            self.assertFalse((outside / "source.zip").exists())
        finally:
            # Remove the junction itself, preserving its target for temp cleanup.
            os.rmdir(junction)

    def test_archive_is_reproducible_across_metadata_changes(self):
        names = release.build_release(self.root, self.output)
        original = self.output.read_bytes()
        for name in names:
            path = self.root / name
            os.utime(path, (1700000000, 1700000000))
            path.chmod(0o755)
        second = self.directory / "second.zip"
        release.build_release(self.root, second)
        self.assertEqual(original, second.read_bytes())
        with zipfile.ZipFile(second) as archive:
            for entry in archive.infolist():
                self.assertEqual(entry.date_time, release.FIXED_TIMESTAMP)
                self.assertEqual(stat.S_IMODE(entry.external_attr >> 16), 0o644)
                self.assertEqual(entry.compress_type, zipfile.ZIP_STORED)

    def test_empty_manifest_and_manifest_traversal_are_rejected(self):
        self.manifest("# No files")
        with self.assertRaisesRegex(release.ReleaseError, "no source"):
            release.build_release(self.root, self.output)
        with self.assertRaises(release.ReleaseError):
            release.build_release(self.root, self.output, "../manifest.txt")


if __name__ == "__main__":
    unittest.main()
