"""Release archives are reproducible, bounded, and independently verifiable."""
import copy
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ascend_release", ROOT / "scripts/build_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ascend-release-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "source"
        for relative in release.REQUIRED_FILES:
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("1.0.0\n" if relative == "VERSION" else relative + " fixture\n", encoding="utf-8")
        self.output = self.directory / "dist"
        self.archive = release.build_release(self.source, self.output)

    def entries(self):
        with zipfile.ZipFile(self.archive) as package:
            return [(copy.copy(entry), package.read(entry)) for entry in package.infolist()]

    def rewrite(self, entries):
        target = self.directory / "modified" / self.archive.name
        target.parent.mkdir(exist_ok=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as package:
                for name, contents in entries:
                    if isinstance(name, str):
                        original = name
                        name = zipfile.ZipInfo(name)
                        # Construct hostile names without the Windows writer
                        # normalizing them before the verifier can see them.
                        name.filename = original
                    package.writestr(name, contents)
        return target

    def test_roundtrip_and_manifest_cover_only_allowed_payload(self):
        manifest = release.verify_release(self.archive, self.output / "SHA256SUMS")
        self.assertEqual(manifest["version"], "1.0.0")
        self.assertEqual(set(manifest["files"]), set(release.REQUIRED_FILES))
        self.assertEqual(manifest, json.loads((self.output / release.MANIFEST_NAME).read_text()))
        with zipfile.ZipFile(self.archive) as package:
            inside = package.read("ascend-1.0.0/" + release.MANIFEST_NAME)
            self.assertEqual(inside, (self.output / release.MANIFEST_NAME).read_bytes())
            self.assertEqual(package.namelist(), sorted(package.namelist()))
            for entry in package.infolist():
                self.assertEqual(entry.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertTrue(stat.S_ISREG(entry.external_attr >> 16))

    def test_two_builds_are_byte_identical_and_do_not_include_local_files(self):
        for relative in (".git/config", ".local/private.txt", "examples/snapshot.json",
                         "skills/ascend/__pycache__/private.pyc", "skills/ascend/private.json"):
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("PRIVATE-HOST-PATH-SENTINEL", encoding="utf-8")
        second = release.build_release(self.source, self.directory / "second")
        self.assertEqual(self.archive.read_bytes(), second.read_bytes())
        for path in self.output.iterdir():
            self.assertNotIn(b"PRIVATE-HOST-PATH-SENTINEL", path.read_bytes())
            self.assertNotIn(str(self.source).encode(), path.read_bytes())

    def test_license_and_optional_manifests_are_included_only_if_present(self):
        for relative in release.OPTIONAL_FILES:
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("optional fixture\n", encoding="utf-8")
        archive = release.build_release(self.source, self.directory / "licensed")
        manifest = release.verify_release(archive)
        self.assertEqual(set(manifest["files"]), set(release.REQUIRED_FILES + release.OPTIONAL_FILES))

    def test_installed_skill_keeps_its_license_even_without_root_license(self):
        with zipfile.ZipFile(self.archive) as package:
            self.assertEqual(package.read("ascend-1.0.0/skills/ascend/LICENSE"),
                             (self.source / "skills/ascend/LICENSE").read_bytes())
        self.assertIn("skills/ascend/LICENSE", release.verify_release(self.archive)["files"])

    def test_declared_skill_version_must_match_authoritative_version(self):
        skill = self.source / "skills/ascend/SKILL.md"
        for index, declared in enumerate(('"1.0.0"', "'1.0.0'", "1.0.0 # comment")):
            with self.subTest(declared=declared):
                skill.write_text(f"---\nname: ascend\nmetadata:\n  version: {declared}\n---\n# ASCEND\n",
                                 encoding="utf-8")
                archive = release.build_release(self.source, self.directory / f"metadata-{index}")
                self.assertEqual(release.verify_release(archive)["version"], "1.0.0")
        skill.write_text('---\nmetadata:\n  version: "0.9.0"\n---\n', encoding="utf-8")
        with self.assertRaisesRegex(release.ReleaseError, "metadata.version"):
            release.build_release(self.source, self.directory / "mismatched")

    def test_identical_rebuild_is_idempotent(self):
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.output.iterdir()}
        self.assertEqual(release.build_release(self.source, self.output), self.archive)
        after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.output.iterdir()}
        self.assertEqual(before, after)

    def test_different_build_cannot_overwrite_existing_release(self):
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        (self.source / "README.md").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(release.ReleaseError, "overwrite"):
            release.build_release(self.source, self.output)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})

    def test_conflicting_sidecar_cannot_publish_partial_release(self):
        output = self.directory / "conflict"
        output.mkdir()
        (output / "SHA256SUMS").write_text("existing", encoding="utf-8")
        with self.assertRaises(release.ReleaseError):
            release.build_release(self.source, output)
        self.assertEqual([path.name for path in output.iterdir()], ["SHA256SUMS"])

    def test_missing_required_source_is_an_error_without_publishing(self):
        (self.source / release.SKILL_FILES[0]).unlink()
        output = self.directory / "missing"
        with self.assertRaisesRegex(release.ReleaseError, "missing"):
            release.build_release(self.source, output)
        self.assertFalse(output.exists())

    def test_unsafe_version_cannot_select_output_path(self):
        for version in ("../../outside", "01.0.0", "1.0", "v1.0.0", "1.0.0\nmalicious"):
            with self.subTest(version=version):
                (self.source / "VERSION").write_text(version, encoding="utf-8")
                with self.assertRaises(release.ReleaseError):
                    release.build_release(self.source, self.directory / "invalid")

    def test_checksum_mismatch_and_duplicate_checksum_entries_are_rejected(self):
        sums = self.directory / "SHA256SUMS"
        for text in ("0" * 64 + "  " + self.archive.name + "\n",
                     (self.output / "SHA256SUMS").read_text() * 2,
                     "invalid checksum\n"):
            with self.subTest(text=text[:20]):
                sums.write_text(text, encoding="utf-8")
                with self.assertRaises(release.ReleaseError):
                    release.verify_release(self.archive, sums)

    def test_modified_payload_is_rejected_without_trusting_checksum(self):
        entries = self.entries()
        entries = [(entry, contents + b"modified" if entry.filename.endswith("README.md") else contents)
                   for entry, contents in entries]
        with self.assertRaisesRegex(release.ReleaseError, "hash mismatch"):
            release.verify_release(self.rewrite(entries))

    def test_added_or_missing_payload_and_missing_manifest_are_rejected(self):
        original = self.entries()
        variants = [original + [("ascend-1.0.0/extra.txt", b"extra")],
                    [(entry, data) for entry, data in original if not entry.filename.endswith("SKILL.md")],
                    [(entry, data) for entry, data in original if not entry.filename.endswith(release.MANIFEST_NAME)]]
        for entries in variants:
            with self.subTest(count=len(entries)):
                with self.assertRaises(release.ReleaseError):
                    release.verify_release(self.rewrite(entries))

    def test_consistently_resigned_unsupported_payload_is_rejected(self):
        entries = []
        for entry, contents in self.entries():
            if entry.filename.endswith(release.MANIFEST_NAME):
                manifest = json.loads(contents)
                manifest["files"]["private.json"] = release.sha256(b"private")
                contents = json.dumps(manifest).encode()
            entries.append((entry, contents))
        entries.append(("ascend-1.0.0/private.json", b"private"))
        with self.assertRaisesRegex(release.ReleaseError, "unsupported"):
            release.verify_release(self.rewrite(entries))

    def test_duplicate_paths_and_case_collisions_are_rejected(self):
        original = self.entries()
        first = original[0]
        for additional in (first, (first[0].filename.upper(), first[1])):
            with self.subTest(path=str(additional[0])):
                with self.assertRaisesRegex(release.ReleaseError, "collid|duplicate"):
                    release.verify_release(self.rewrite(original + [additional]))

    def test_path_traversal_and_windows_path_ambiguities_are_rejected(self):
        paths = ("../outside", "/absolute", "ascend-1.0.0/../outside",
                 "ascend-1.0.0/C:drive", "ascend-1.0.0/evil\\file",
                 "ascend-1.0.0/./file", "ascend-1.0.0//file", "ascend-1.0.0/file. ",
                 "ascend-1.0.0/NUL\x00hidden")
        for path in paths:
            with self.subTest(path=path):
                with self.assertRaisesRegex(release.ReleaseError, "unsafe"):
                    release.verify_release(self.rewrite(self.entries() + [(path, b"bad")]))

    def test_symlink_and_special_file_are_rejected(self):
        for mode in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR):
            with self.subTest(mode=mode):
                entry = zipfile.ZipInfo("ascend-1.0.0/link")
                entry.create_system = 3
                entry.external_attr = (mode | 0o644) << 16
                with self.assertRaisesRegex(release.ReleaseError, "regular|special"):
                    release.verify_release(self.rewrite(self.entries() + [(entry, b"target")]))

    def test_file_directory_collision_and_directory_entry_are_rejected(self):
        for name in ("ascend-1.0.0/skills", "ascend-1.0.0/skills/"):
            with self.subTest(name=name):
                with self.assertRaises(release.ReleaseError):
                    release.verify_release(self.rewrite(self.entries() + [(name, b"")]))

    def test_archive_root_and_filename_must_agree_with_version(self):
        renamed = self.directory / "renamed.zip"
        renamed.write_bytes(self.archive.read_bytes())
        with self.assertRaisesRegex(release.ReleaseError, "agree"):
            release.verify_release(renamed)
        entries = [(entry.filename.replace("ascend-1.0.0/", "ascend-2.0.0/"), data)
                   for entry, data in self.entries()]
        with self.assertRaisesRegex(release.ReleaseError, "agree"):
            release.verify_release(self.rewrite(entries))

    def test_manifest_duplicate_keys_and_invalid_schema_are_rejected(self):
        for contents in (b'{"version":"1.0.0","version":"1.0.0","files":{}}',
                         b'{"version":"1.0.0","files":[],"unexpected":true}',
                         b'[]', b'{invalid'):
            with self.subTest(contents=contents):
                entries = [(entry, contents if entry.filename.endswith(release.MANIFEST_NAME) else data)
                           for entry, data in self.entries()]
                with self.assertRaises(release.ReleaseError):
                    release.verify_release(self.rewrite(entries))

    def test_zip_bomb_and_total_expanded_size_are_bounded(self):
        entries = self.entries() + [("ascend-1.0.0/bomb", b"0" * (release.MAX_FILE_BYTES + 1))]
        with self.assertRaisesRegex(release.ReleaseError, "size limit"):
            release.verify_release(self.rewrite(entries))
        with mock.patch.object(release, "MAX_TOTAL_BYTES", 512):
            with self.assertRaisesRegex(release.ReleaseError, "total expanded"):
                release.verify_release(self.archive)

    def test_archive_file_size_and_entry_count_are_bounded(self):
        with mock.patch.object(release, "MAX_ARCHIVE_BYTES", 16):
            with self.assertRaisesRegex(release.ReleaseError, "size limit"):
                release.verify_release(self.archive)
        with mock.patch.object(release, "MAX_ENTRIES", 2):
            with self.assertRaisesRegex(release.ReleaseError, "number of entries"):
                release.verify_release(self.archive)

    def test_corrupt_zip_is_rejected(self):
        path = self.directory / "broken.zip"
        path.write_bytes(b"not a ZIP archive")
        with self.assertRaises(release.ReleaseError):
            release.verify_release(path)

    def test_source_symlink_is_rejected(self):
        target = self.directory / "outside.txt"
        target.write_text("outside", encoding="utf-8")
        source = self.source / "README.md"
        source.unlink()
        try:
            source.symlink_to(target)
        except OSError:
            self.skipTest("This Windows account cannot create symlinks")
        with self.assertRaises(release.ReleaseError):
            release.build_release(self.source, self.directory / "linked")

    def test_verifier_writes_nothing_and_cli_runs_from_arbitrary_directory(self):
        before = {path.relative_to(self.directory) for path in self.directory.rglob("*")}
        release.verify_release(self.archive, self.output / "SHA256SUMS")
        completed = subprocess.run([sys.executable, str(ROOT / "scripts/build_release.py"),
                                    "--verify", str(self.archive), "--checksums",
                                    str(self.output / "SHA256SUMS")], cwd=self.directory,
                                   capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Verified ASCEND 1.0.0", completed.stdout)
        self.assertEqual(before, {path.relative_to(self.directory) for path in self.directory.rglob("*")})

    def test_cli_requires_checksum_for_verification(self):
        completed = subprocess.run([sys.executable, str(ROOT / "scripts/build_release.py"),
                                    "--verify", str(self.archive)], cwd=self.directory,
                                   capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("requires --checksums", completed.stderr)


if __name__ == "__main__":
    unittest.main()
