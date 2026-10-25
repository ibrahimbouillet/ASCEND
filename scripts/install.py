#!/usr/bin/env python3
"""Install ASCEND locally for Codex and Claude Code using Python 3.11+.

No network access or host configuration edits are performed. Existing managed
files must be intact; upgrades preserve the prior installation as a backup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import uuid


MANIFEST = ".ascend-install.json"
SOURCE_ID = "ascend/skill"
REQUIRED_FILES = {
    "SKILL.md", "agents/openai.yaml", "scripts/ascend.py",
    "references/workflow.md", "references/benchmarking.md", "references/data-model.md",
    "assets/dashboard/template.html", "assets/dashboard/app.js", "assets/dashboard/styles.css",
}
VERSION_PATTERN = re.compile(r"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


class InstallError(Exception):
    """A package or destination cannot be safely installed or verified."""


def _absolute(path: Path | str) -> Path:
    # Do not resolve links: the original path must be inspected before use.
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _is_link(info: os.stat_result) -> bool:
    # Windows junctions and other reparse points must be treated as links too.
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _safe_path(path: Path, *, file_ok: bool = False) -> None:
    """Reject links and non-directory ancestors, including Windows junctions."""
    parts = list(reversed(path.parents)) + [path]
    for item in parts:
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if _is_link(info):
            raise InstallError(f"Links and junctions are not allowed: {item}")
        if not stat.S_ISDIR(info.st_mode) and not (
            item == path and file_ok and stat.S_ISREG(info.st_mode)
        ):
            raise InstallError(f"Expected a directory: {item}")


def _version(value: object) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise InstallError("Version must contain three numeric components, for example 1.0.0.")
    return tuple(int(part) for part in match.groups())


def _scan(root: Path, *, source: bool = False) -> tuple[dict[str, bytes], set[str]]:
    """Read regular files without following links; detect unexpected directories."""
    _safe_path(root)
    files: dict[str, bytes] = {}
    directories: set[str] = set()
    if not root.is_dir():
        raise InstallError(f"Missing skill directory: {root}")

    def visit(directory: Path, ignored: bool = False) -> None:
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                item = Path(entry.path)
                info = entry.stat(follow_symlinks=False)
                if _is_link(info):
                    raise InstallError(f"Links and junctions are not allowed: {item}")
                relative = item.relative_to(root).as_posix()
                if stat.S_ISDIR(info.st_mode):
                    excluded = ignored or (source and entry.name == "__pycache__")
                    if not excluded:
                        directories.add(relative)
                    visit(item, excluded)
                elif stat.S_ISREG(info.st_mode):
                    if not ignored and not (source and item.suffix in {".pyc", ".pyo"}):
                        files[relative] = item.read_bytes()
                else:
                    raise InstallError(f"Only regular files and directories are allowed: {item}")

    visit(root)
    return files, directories


def _hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}


def load_package(source_root: Path | str) -> dict:
    """Validate a source checkout or extracted release and snapshot its contents."""
    root = _absolute(source_root)
    _safe_path(root)
    version_file = root / "VERSION"
    _safe_path(version_file, file_ok=True)
    try:
        version = version_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise InstallError("The source package must contain a readable root VERSION file.") from exc
    _version(version)
    version = version.removeprefix("v")
    skill = root / "skills" / "ascend"
    files, _ = _scan(skill, source=True)
    missing = REQUIRED_FILES - files.keys()
    if missing:
        raise InstallError("Incomplete skill package; missing: " + ", ".join(sorted(missing)))
    if MANIFEST in files:
        raise InstallError("Source packages must not contain an installation ownership manifest.")
    try:
        entry = files["SKILL.md"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstallError("SKILL.md must be UTF-8.") from exc
    frontmatter = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", entry, re.DOTALL)
    if not frontmatter or not re.search(r"^name:[ \t]*ascend[ \t]*\r?$", frontmatter[1], re.MULTILINE):
        raise InstallError("SKILL.md must declare name: ascend in its frontmatter.")
    for name, data in files.items():
        if not name.endswith(".md"):
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InstallError(f"Markdown must be UTF-8: {name}") from exc
        for target in re.findall(r"\[[^\]\r\n]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", text):
            parsed = urlsplit(target)
            if parsed.scheme in {"https", "http", "mailto"}:
                continue
            if parsed.scheme or parsed.netloc:
                raise InstallError(f"Unsupported local reference in {name}: {target}")
            local = unquote(parsed.path)
            if not local:
                continue
            reference = _absolute(skill / Path(name).parent / local)
            try:
                relative = reference.relative_to(skill).as_posix()
            except ValueError as exc:
                raise InstallError(f"Reference escapes the skill directory in {name}: {target}") from exc
            if relative not in files:
                raise InstallError(f"Missing package reference in {name}: {target}")
    return {"version": version, "files": files, "hashes": _hashes(files)}


def _manifest(package: dict) -> dict:
    return {"schema_version": 1, "name": "ascend", "source_id": SOURCE_ID,
            "version": package["version"], "files": package["hashes"]}


def verify_installation(destination: Path | str) -> dict:
    """Verify ownership and every installed byte without writing or repairing."""
    destination = _absolute(destination)
    files, directories = _scan(destination)
    if MANIFEST not in files:
        raise InstallError(f"Existing directory is not owned by the ASCEND installer: {destination}")
    try:
        manifest = json.loads(files.pop(MANIFEST))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InstallError(f"Invalid installation manifest: {destination}") from exc
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version", "name", "source_id", "version", "files"
    } or manifest["schema_version"] != 1 or isinstance(manifest["schema_version"], bool) or (
        manifest["name"] != "ascend" or manifest["source_id"] != SOURCE_ID
    ):
        raise InstallError(f"Unrecognized installation ownership manifest: {destination}")
    _version(manifest["version"])
    expected = manifest["files"]
    if not isinstance(expected, dict) or not REQUIRED_FILES <= expected.keys():
        raise InstallError(f"Incomplete installation manifest: {destination}")
    for name, digest in expected.items():
        path = PurePosixPath(name)
        if (not name or "\\" in name or ":" in name or path.is_absolute() or ".." in path.parts
                or path.as_posix() != name or name == MANIFEST
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise InstallError(f"Unsafe file entry in installation manifest: {destination}")
    allowed_dirs = {str(parent) for name in expected for parent in PurePosixPath(name).parents
                    if str(parent) != "."}
    if _hashes(files) != expected or directories != allowed_dirs:
        raise InstallError(f"Managed installation contains modified, missing, or unexpected content: {destination}")
    return manifest


def destinations(host: str, scope: str, *, project: Path | str | None = None,
                 home: Path | str | None = None) -> list[Path]:
    if host not in {"codex", "claude", "both"} or scope not in {"user", "project"}:
        raise InstallError("Choose --host codex|claude|both and --scope user|project.")
    if scope == "project":
        if project is None:
            raise InstallError("--project PATH is required for project scope.")
        if home is not None:
            raise InstallError("--home applies only to user scope.")
        root = _absolute(project)
        _safe_path(root)
        if not root.is_dir():
            raise InstallError("The project directory must already exist.")
    else:
        if project is not None:
            raise InstallError("--project applies only to project scope.")
        root = _absolute(home if home is not None else Path.home())
        _safe_path(root)
    roots = ([".agents", ".claude"] if host == "both" else
             [".agents" if host == "codex" else ".claude"])
    return [root / folder / "skills" / "ascend" for folder in roots]


def _make_parents(parent: Path, created: list[Path]) -> None:
    missing = []
    item = parent
    while not item.exists():
        missing.append(item)
        item = item.parent
    for item in reversed(missing):
        _safe_path(item)
        item.mkdir()
        created.append(item)


def _remove_stage(stage: Path, parent: Path) -> None:
    # Only recursively remove an exact installer-created temporary directory.
    if stage.parent != parent or not stage.name.startswith(".ascend-stage-"):
        raise InstallError("Refusing cleanup outside the installation staging directory.")
    if stage.exists():
        _scan(stage)  # Reject links, including junctions, before recursive cleanup.
        shutil.rmtree(stage)


def install(*, host: str, scope: str, project: Path | str | None = None,
            home: Path | str | None = None, dry_run: bool = False,
            upgrade: bool = False, verify: bool = False,
            source_root: Path | str | None = None) -> list[str]:
    """Preflight every host, then install transactionally with rollback on failure."""
    if verify and (dry_run or upgrade):
        raise InstallError("--verify is read-only and cannot be combined with --dry-run or --upgrade.")
    targets = destinations(host, scope, project=project, home=home)
    if verify:
        return [f"Verified ASCEND {verify_installation(target)['version']}: {target}" for target in targets]
    package = load_package(source_root if source_root is not None else Path(__file__).absolute().parents[1])
    plans = []
    results = []
    for target in targets:
        _safe_path(target)
        old = verify_installation(target) if target.exists() else None
        if old is not None:
            if _version(old["version"]) > _version(package["version"]):
                raise InstallError(f"Refusing version downgrade at {target}.")
            if _version(old["version"]) == _version(package["version"]):
                if old["files"] != package["hashes"]:
                    raise InstallError(f"Version {package['version']} has different package content at {target}.")
                results.append(f"Already installed and verified ASCEND {package['version']}: {target}")
                continue
            if not upgrade:
                raise InstallError(f"ASCEND {old['version']} is installed at {target}; use --upgrade to preserve it as a backup.")
        plans.append({"target": target, "old": old, "stage": None, "backup": None, "active": False})
    if dry_run:
        return results + [f"Would {'upgrade' if plan['old'] else 'install'} ASCEND {package['version']}: {plan['target']}"
                          for plan in plans]
    created: list[Path] = []
    try:
        # Stage all destinations before switching either host.
        for plan in plans:
            parent = plan["target"].parent
            _make_parents(parent, created)
            _safe_path(parent)
            stage = Path(tempfile.mkdtemp(prefix=".ascend-stage-", dir=parent))
            plan["stage"] = stage
            for name, data in package["files"].items():
                output = stage / name
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(data)
            (stage / MANIFEST).write_text(json.dumps(_manifest(package), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            verify_installation(stage)
        for plan in plans:
            target, stage = plan["target"], plan["stage"]
            _safe_path(target)
            if plan["old"]:
                if verify_installation(target) != plan["old"]:
                    raise InstallError(f"Installation changed during preflight: {target}")
                backup = target.with_name(f".ascend-backup-{plan['old']['version']}-{uuid.uuid4().hex}")
                if os.path.lexists(backup):
                    raise InstallError(f"Backup destination already exists; retry with a new backup name: {backup}")
                plan["backup"] = backup
                os.replace(target, backup)
            elif target.exists():
                raise InstallError(f"Destination appeared during installation: {target}")
            os.replace(stage, target)
            plan["active"] = True
        for plan in plans:
            suffix = f"; previous version preserved at {plan['backup']}" if plan["backup"] else ""
            results.append(f"Installed ASCEND {package['version']}: {plan['target']}{suffix}")
        return results
    except Exception as exc:
        rollback_errors = []
        for plan in reversed(plans):
            try:
                if plan["active"]:
                    if verify_installation(plan["target"]) != _manifest(package):
                        raise InstallError("Installed content changed; preserving it for manual recovery.")
                    os.replace(plan["target"], plan["stage"])
                    plan["active"] = False
                if plan["backup"] and plan["backup"].exists():
                    if plan["target"].exists():
                        raise InstallError("Destination is occupied; preserving the previous version backup.")
                    os.replace(plan["backup"], plan["target"])
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        for plan in plans:
            if plan["stage"] is not None:
                try:
                    _remove_stage(plan["stage"], plan["target"].parent)
                except Exception as cleanup_exc:
                    rollback_errors.append(str(cleanup_exc))
        for parent in reversed(created):
            try:
                parent.rmdir()  # Remove only empty directories created by this transaction.
            except OSError:
                pass
        detail = "; rollback needs manual recovery: " + "; ".join(rollback_errors) if rollback_errors else "; no partial installation retained"
        raise InstallError(f"Installation failed: {exc}{detail}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("codex", "claude", "both"), required=True)
    parser.add_argument("--scope", choices=("user", "project"), required=True)
    parser.add_argument("--project", type=Path, help="Existing project root; required for project scope")
    parser.add_argument("--home", type=Path, help="Custom user home for user scope; defaults to Path.home()")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview without any writes")
    parser.add_argument("--upgrade", action="store_true", help="Upgrade an intact managed install, preserving a backup")
    parser.add_argument("--verify", action="store_true", help="Read-only ownership and file-integrity verification")
    args = parser.parse_args(argv)
    try:
        for result in install(**vars(args)):
            print(result)
    except (InstallError, OSError, ValueError) as exc:
        print(f"ASCEND installer: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
