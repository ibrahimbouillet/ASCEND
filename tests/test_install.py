"""Isolated installer contracts: ownership, safe upgrades, and two-host rollback."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).absolute().parents[1]
SPEC = importlib.util.spec_from_file_location("ascend_installer", ROOT / "scripts" / "install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def tree(path):
    if not path.exists():
        return None
    return {item.relative_to(path).as_posix(): item.read_bytes()
            for item in path.rglob("*") if item.is_file()}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ascend-install-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "release"
        self.skill = self.source / "skills" / "ascend"
        for name in installer.REQUIRED_FILES:
            file = self.skill / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("Fixture content.\n", encoding="utf-8")
        (self.skill / "SKILL.md").write_text(
            "---\nname: ascend\ndescription: Test fixture.\n---\n# ASCEND\n"
            "Read [workflow](references/workflow.md).\n", encoding="utf-8")
        (self.source / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        self.home = self.root / "isolated-home"
        self.project = self.root / "project"
        self.project.mkdir()

    def install(self, **kwargs):
        options = {"host": "both", "scope": "user", "home": self.home,
                   "source_root": self.source}
        options.update(kwargs)
        return installer.install(**options)

    def target(self, host="codex"):
        return self.home / (".agents" if host == "codex" else ".claude") / "skills" / "ascend"

    def bump(self, version="1.1.0"):
        (self.source / "VERSION").write_text(version, encoding="utf-8")
        (self.skill / "references" / "workflow.md").write_text("Updated workflow.\n", encoding="utf-8")

    def test_fresh_both_hosts_have_identical_content_and_private_path_free_manifests(self):
        result = self.install()
        self.assertEqual(len(result), 2)
        self.assertEqual(tree(self.target()), tree(self.target("claude")))
        manifest = installer.verify_installation(self.target())
        self.assertEqual(manifest["version"], "1.0.0")
        self.assertEqual(set(manifest["files"]), installer.REQUIRED_FILES)
        encoded = (self.target() / installer.MANIFEST).read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn(str(Path.home()), encoded)
        self.assertEqual(manifest["source_id"], "ascend/skill")

    def test_project_scope_uses_existing_project_and_does_not_touch_user_home(self):
        self.install(scope="project", project=self.project, home=None)
        for folder in (".agents", ".claude"):
            installer.verify_installation(self.project / folder / "skills" / "ascend")
        self.assertFalse(self.home.exists())

    def test_single_host_does_not_create_other_host(self):
        self.install(host="claude")
        self.assertTrue(self.target("claude").is_dir())
        self.assertFalse((self.home / ".agents").exists())

    def test_default_user_home_is_selected_without_global_configuration_changes(self):
        with mock.patch.object(installer.Path, "home", return_value=self.home):
            installer.install(host="codex", scope="user", source_root=self.source)
        self.assertTrue(self.target().is_dir())
        self.assertEqual(set(tree(self.home)), {
            ".agents/skills/ascend/" + name for name in installer.REQUIRED_FILES | {installer.MANIFEST}
        })

    def test_dry_run_performs_no_writes_even_when_home_parents_do_not_exist(self):
        before = tree(self.root)
        output = self.install(dry_run=True)
        self.assertEqual(len(output), 2)
        self.assertTrue(all(line.startswith("Would install") for line in output))
        self.assertFalse(self.home.exists())
        self.assertEqual(tree(self.root), before)

    def test_identical_version_is_idempotent_without_writes(self):
        self.install()
        before = tree(self.home)
        with mock.patch.object(installer.Path, "write_bytes", side_effect=AssertionError("Unexpected write")), \
                mock.patch.object(installer.Path, "write_text", side_effect=AssertionError("Unexpected write")), \
                mock.patch.object(installer.os, "replace", side_effect=AssertionError("Unexpected move")), \
                mock.patch.object(installer.tempfile, "mkdtemp", side_effect=AssertionError("Unexpected staging")):
            result = self.install()
        self.assertTrue(all(line.startswith("Already installed") for line in result))
        self.assertEqual(tree(self.home), before)

    def test_unowned_second_host_is_preflighted_before_any_write(self):
        collision = self.target("claude")
        collision.mkdir(parents=True)
        (collision / "custom.txt").write_text("Owner's work", encoding="utf-8")
        before = tree(self.home)
        with self.assertRaisesRegex(installer.InstallError, "not owned"):
            self.install(upgrade=True)
        self.assertEqual(tree(self.home), before)
        self.assertFalse((self.home / ".agents").exists())

    def test_empty_unowned_directory_is_preserved(self):
        self.target().mkdir(parents=True)
        with self.assertRaisesRegex(installer.InstallError, "not owned"):
            self.install(host="codex", upgrade=True)
        self.assertTrue(self.target().is_dir())
        self.assertEqual(list(self.target().iterdir()), [])

    def test_destination_file_collision_is_preserved(self):
        self.target().parent.mkdir(parents=True)
        self.target().write_text("Owner's file", encoding="utf-8")
        with self.assertRaises(installer.InstallError):
            self.install(host="codex")
        self.assertEqual(self.target().read_text(encoding="utf-8"), "Owner's file")

    def test_tampered_managed_files_cannot_be_verified_or_upgraded(self):
        self.install()
        (self.target() / "SKILL.md").write_text("Local customization", encoding="utf-8")
        before = tree(self.home)
        self.bump()
        for options in ({"verify": True}, {"upgrade": True}, {"dry_run": True, "upgrade": True}):
            with self.subTest(options=options), self.assertRaisesRegex(installer.InstallError, "modified"):
                self.install(**options)
        self.assertEqual(tree(self.home), before)

    def test_unexpected_file_is_not_silently_discarded(self):
        self.install()
        (self.target() / "notes.txt").write_text("Keep me", encoding="utf-8")
        self.bump()
        with self.assertRaisesRegex(installer.InstallError, "unexpected"):
            self.install(upgrade=True)
        self.assertEqual((self.target() / "notes.txt").read_text(), "Keep me")

    def test_unexpected_empty_directory_is_not_silently_discarded(self):
        self.install()
        (self.target() / "my-notes").mkdir()
        with self.assertRaisesRegex(installer.InstallError, "unexpected"):
            self.install(verify=True)

    def test_missing_file_and_corrupt_manifest_are_rejected(self):
        self.install()
        (self.target() / "agents" / "openai.yaml").unlink()
        with self.assertRaisesRegex(installer.InstallError, "missing"):
            self.install(verify=True)
        (self.target("claude") / installer.MANIFEST).write_text("not JSON", encoding="utf-8")
        with self.assertRaisesRegex(installer.InstallError, "Invalid installation manifest"):
            self.install(host="claude", verify=True)

    def test_manifest_ownership_and_path_entries_are_validated(self):
        self.install(host="codex")
        file = self.target() / installer.MANIFEST
        original = json.loads(file.read_text())
        variants = []
        for field, value in (("source_id", "someone-else"), ("schema_version", True), ("version", "1.0")):
            candidate = dict(original)
            candidate[field] = value
            variants.append(candidate)
        for name in ("../outside", "/absolute", "C:/private", "a/../SKILL.md", "a\\b"):
            candidate = dict(original, files=dict(original["files"]))
            candidate["files"][name] = "0" * 64
            variants.append(candidate)
        for candidate in variants:
            with self.subTest(candidate=candidate):
                file.write_text(json.dumps(candidate))
                with self.assertRaises(installer.InstallError):
                    self.install(host="codex", verify=True)

    def test_upgrade_requires_explicit_flag(self):
        self.install()
        before = tree(self.home)
        self.bump()
        with self.assertRaisesRegex(installer.InstallError, "use --upgrade"):
            self.install()
        self.assertEqual(tree(self.home), before)

    def test_upgrade_preserves_exact_old_content_and_unique_backups(self):
        self.install()
        old = tree(self.target())
        self.bump()
        self.install(upgrade=True)
        backups = list(self.target().parent.glob(".ascend-backup-1.0.0-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(tree(backups[0]), old)
        self.assertEqual(installer.verify_installation(self.target())["version"], "1.1.0")
        self.bump("1.2.0")
        self.install(upgrade=True)
        self.assertEqual(len(list(self.target().parent.glob(".ascend-backup-*"))), 2)
        self.assertEqual(tree(backups[0]), old)
        self.assertEqual(list(self.home.rglob(".ascend-stage-*")), [])

    def test_dry_run_upgrade_preserves_every_byte_and_creates_no_backup(self):
        self.install()
        before = tree(self.home)
        self.bump()
        result = self.install(dry_run=True, upgrade=True)
        self.assertTrue(all(line.startswith("Would upgrade") for line in result))
        self.assertEqual(tree(self.home), before)
        self.assertEqual(list(self.home.rglob(".ascend-backup-*")), [])

    def test_downgrade_is_refused_even_with_upgrade_flag(self):
        self.install()
        before = tree(self.home)
        self.bump("0.9.0")
        with self.assertRaisesRegex(installer.InstallError, "downgrade"):
            self.install(upgrade=True)
        self.assertEqual(tree(self.home), before)

    def test_same_version_different_source_is_refused(self):
        self.install()
        before = tree(self.home)
        (self.skill / "scripts" / "ascend.py").write_text("Changed without version bump")
        with self.assertRaisesRegex(installer.InstallError, "different package content"):
            self.install(upgrade=True)
        self.assertEqual(tree(self.home), before)

    def test_verify_is_read_only_and_independent_of_source_version(self):
        self.install()
        before = tree(self.home)
        (self.source / "VERSION").unlink()
        with mock.patch.object(installer.Path, "write_bytes", side_effect=AssertionError("Unexpected write")), \
                mock.patch.object(installer.Path, "write_text", side_effect=AssertionError("Unexpected write")):
            result = self.install(verify=True)
        self.assertTrue(all(line.startswith("Verified ASCEND 1.0.0") for line in result))
        self.assertEqual(tree(self.home), before)

    def test_verify_missing_installation_does_not_create_anything(self):
        with self.assertRaises(installer.InstallError):
            self.install(verify=True)
        self.assertFalse(self.home.exists())

    def test_verify_rejects_mutating_or_preview_flags(self):
        for options in ({"verify": True, "upgrade": True}, {"verify": True, "dry_run": True}):
            with self.subTest(options=options), self.assertRaisesRegex(installer.InstallError, "read-only"):
                self.install(**options)

    def test_second_host_activation_failure_rolls_back_fresh_first_host(self):
        replace = os.replace

        def fail_second(source, target):
            if Path(source).name.startswith(".ascend-stage-") and Path(target) == self.target("claude"):
                raise OSError("Simulated second-host activation failure")
            return replace(source, target)

        with mock.patch.object(installer.os, "replace", side_effect=fail_second):
            with self.assertRaisesRegex(installer.InstallError, "no partial installation retained"):
                self.install()
        self.assertFalse(self.home.exists())

    def test_second_host_activation_failure_restores_both_previous_versions(self):
        self.install()
        before = tree(self.home)
        self.bump()
        replace = os.replace

        def fail_second(source, target):
            if Path(source).name.startswith(".ascend-stage-") and Path(target) == self.target("claude"):
                raise OSError("Simulated upgrade activation failure")
            return replace(source, target)

        with mock.patch.object(installer.os, "replace", side_effect=fail_second):
            with self.assertRaisesRegex(installer.InstallError, "no partial installation retained"):
                self.install(upgrade=True)
        self.assertEqual(tree(self.home), before)
        self.assertEqual(list(self.home.rglob(".ascend-backup-*")), [])
        self.assertEqual(list(self.home.rglob(".ascend-stage-*")), [])

    def test_staging_write_failure_leaves_both_existing_hosts_intact(self):
        self.install()
        before = tree(self.home)
        self.bump()
        write = Path.write_bytes

        def fail_second(path, data):
            if ".claude" in path.parts and any(part.startswith(".ascend-stage-") for part in path.parts):
                raise OSError("Simulated disk failure")
            return write(path, data)

        with mock.patch.object(installer.Path, "write_bytes", fail_second):
            with self.assertRaisesRegex(installer.InstallError, "no partial installation retained"):
                self.install(upgrade=True)
        self.assertEqual(tree(self.home), before)
        self.assertEqual(list(self.home.rglob(".ascend-stage-*")), [])

    def test_rollback_failure_preserves_backup_and_explains_manual_recovery(self):
        self.install()
        old = tree(self.target("claude"))
        self.bump()
        replace = os.replace

        def fail_second_and_restore(source, target):
            if Path(target) == self.target("claude"):
                raise OSError("Simulated destination unavailable")
            return replace(source, target)

        with mock.patch.object(installer.os, "replace", side_effect=fail_second_and_restore):
            with self.assertRaisesRegex(installer.InstallError, "manual recovery"):
                self.install(upgrade=True)
        backups = list(self.target("claude").parent.glob(".ascend-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(tree(backups[0]), old)
        self.assertEqual(installer.verify_installation(self.target())["version"], "1.0.0")

    def test_bad_package_layout_or_version_fails_before_writes(self):
        (self.skill / "agents" / "openai.yaml").unlink()
        with self.assertRaisesRegex(installer.InstallError, "Incomplete skill package"):
            self.install()
        self.assertFalse(self.home.exists())
        (self.skill / "agents" / "openai.yaml").write_text("restored")
        for value in ("", "1.0", "v1.0.0-rc1", "01.0.0", "../../outside"):
            (self.source / "VERSION").write_text(value)
            with self.subTest(value=value), self.assertRaises(installer.InstallError):
                self.install()
        self.assertFalse(self.home.exists())

    def test_v_prefixed_source_version_is_normalized(self):
        (self.source / "VERSION").write_text("v1.0.0\n")
        self.install(host="codex")
        self.assertEqual(installer.verify_installation(self.target())["version"], "1.0.0")

    def test_wrong_skill_name_and_escaping_or_missing_references_are_rejected(self):
        file = self.skill / "SKILL.md"
        original = file.read_text()
        for text in (original.replace("name: ascend", "name: another"),
                     original.replace("name: ascend", "name: another") + "name: ascend\n",
                     original + "[escape](../../private.md)\n",
                     original + "[missing](references/missing.md)\n",
                     original + "[encoded escape](%2e%2e/private.md)\n"):
            file.write_text(text)
            with self.subTest(text=text), self.assertRaises(installer.InstallError):
                self.install()
        self.assertFalse(self.home.exists())

    def test_python_caches_are_excluded_from_installed_payload(self):
        cache = self.skill / "scripts" / "__pycache__"
        cache.mkdir()
        (cache / "ascend.cpython-314.pyc").write_bytes(b"generated")
        (self.skill / "scripts" / "loose.pyc").write_bytes(b"generated")
        self.install(host="codex")
        self.assertEqual(set(installer.verify_installation(self.target())["files"]), installer.REQUIRED_FILES)

    def make_link(self, link, target, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except OSError:
            self.skipTest("Creating symbolic links requires privileges unavailable on this host.")

    def test_source_symlink_is_rejected_including_ignored_caches(self):
        outside = self.root / "outside.txt"
        outside.write_text("private")
        self.make_link(self.skill / "leak.txt", outside)
        with self.assertRaisesRegex(installer.InstallError, "Links and junctions"):
            self.install()
        self.assertFalse(self.home.exists())

    def test_destination_ancestor_symlink_is_rejected_without_touching_target(self):
        self.home.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        self.make_link(self.home / ".agents", outside, directory=True)
        with self.assertRaisesRegex(installer.InstallError, "Links and junctions"):
            self.install(host="codex")
        self.assertEqual(list(outside.iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "Windows junction check")
    def test_destination_ancestor_windows_junction_is_rejected(self):
        self.home.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        junction = self.home / ".agents"
        command = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                                 capture_output=True, text=True)
        if command.returncode:
            self.skipTest("Could not create an isolated Windows junction.")
        try:
            with self.assertRaisesRegex(installer.InstallError, "Links and junctions"):
                self.install(host="codex")
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            junction.rmdir()

    def test_invalid_scope_arguments_are_rejected(self):
        combinations = ({"host": "invalid"}, {"scope": "invalid"},
                        {"scope": "project", "project": None, "home": None},
                        {"scope": "project", "project": self.project},
                        {"project": self.project},
                        {"scope": "project", "project": self.root / "missing", "home": None})
        for options in combinations:
            with self.subTest(options=options), self.assertRaises(installer.InstallError):
                self.install(**options)

    def test_cli_runs_from_extracted_release_root_with_spaces(self):
        scripts = self.source / "scripts"
        scripts.mkdir()
        shutil.copyfile(ROOT / "scripts" / "install.py", scripts / "install.py")
        home = self.root / "home with spaces"
        command = [sys.executable, str(scripts / "install.py"), "--host", "both", "--scope", "user",
                   "--home", str(home)]
        preview = subprocess.run(command + ["--dry-run"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(home.exists())
        installed = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        verified = subprocess.run(command + ["--verify"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(verified.stdout.count("Verified ASCEND 1.0.0"), 2)


if __name__ == "__main__":
    unittest.main()
