#!/usr/bin/env python3
"""Build and verify ASCEND releases without network access or extraction.

Run from any directory. The payload is an allowlist, so project snapshots,
development files, credentials, and local captures cannot enter an archive.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
SKILL_FILES = (
    "skills/ascend/SKILL.md",
    "skills/ascend/LICENSE",
    "skills/ascend/agents/openai.yaml",
    "skills/ascend/references/benchmarking.md",
    "skills/ascend/references/data-model.md",
    "skills/ascend/references/workflow.md",
    "skills/ascend/scripts/ascend.py",
    "skills/ascend/assets/dashboard/app.js",
    "skills/ascend/assets/dashboard/styles.css",
    "skills/ascend/assets/dashboard/template.html",
)
REQUIRED_FILES = ("VERSION", "README.md", "INSTALL.md", "scripts/install.py", "scripts/build_release.py") + SKILL_FILES
OPTIONAL_FILES = ("LICENSE", ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json")
MANIFEST_NAME = "release-manifest.json"
MAX_ENTRIES = 256
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 72 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
VERSION_RE = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?\Z")
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


class ReleaseError(ValueError):
    """The release violates the packaging or integrity contract."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _version(data: bytes) -> str:
    try:
        version = data.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise ReleaseError("VERSION must be UTF-8") from error
    if not VERSION_RE.fullmatch(version):
        raise ReleaseError("VERSION must contain a semantic version, such as 1.0.0")
    return version


def _json(data: bytes) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ReleaseError("Manifest contains duplicate JSON keys")
            result[key] = value
        return result

    try:
        value = json.loads(data, object_pairs_hook=unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseError("Invalid release manifest JSON") from error
    if not isinstance(value, dict):
        raise ReleaseError("Release manifest must be an object")
    return value


def _check_skill_version(data: bytes, expected: str) -> None:
    """Check the conventional block-style metadata.version scalar, if present.

    VERSION is authoritative. This deliberately is not a general YAML parser;
    ASCEND's frontmatter uses a simple metadata block and a scalar version.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReleaseError("SKILL.md must be UTF-8") from error
    frontmatter = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
    if frontmatter is None:
        return
    in_metadata = False
    versions = []
    for line in frontmatter[1].splitlines():
        if line and not line[0].isspace() and not line.startswith("#"):
            in_metadata = re.fullmatch(r"metadata:\s*(?:#.*)?", line) is not None
        if in_metadata:
            match = re.fullmatch(r"[ \t]+version:\s*(.*?)\s*", line)
            if match:
                value = match[1].split(" #", 1)[0].strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                versions.append(value)
    if versions and (len(versions) != 1 or versions[0] != expected):
        raise ReleaseError("SKILL.md metadata.version does not agree with VERSION")


def _safe_name(name: str) -> None:
    parts = name.split("/")
    if (not name or any(part in ("", ".", "..") for part in parts)
            or "\\" in name or ":" in name
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or any(part.rstrip(" .") != part for part in parts)):
        raise ReleaseError("Archive contains an unsafe path")


def _read_source(root: Path, relative: str) -> bytes:
    path = root / relative
    if not path.is_file():
        raise ReleaseError(f"Required release source is missing: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ReleaseError(f"Release source escapes the source tree: {relative}")
    current = path
    while current != root:
        if current.is_symlink():
            raise ReleaseError(f"Release source must not be a symlink: {relative}")
        current = current.parent
    with path.open("rb") as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ReleaseError(f"Release source exceeds the file size limit: {relative}")
    return data


def _verify_checksum(archive: Path, data: bytes, checksums: Path) -> None:
    if checksums.stat().st_size > MAX_MANIFEST_BYTES:
        raise ReleaseError("Checksum file exceeds its size limit")
    try:
        lines = checksums.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ReleaseError("Checksum file must be UTF-8") from error
    matching = []
    for line in lines:
        if not line:
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\\s]+)", line)
        if match is None:
            raise ReleaseError("Invalid SHA256SUMS entry")
        if match[2] == archive.name:
            matching.append(match[1])
    if len(matching) != 1 or matching[0] != sha256(data):
        raise ReleaseError("Archive checksum does not match SHA256SUMS")


def verify_release(archive: Path, checksums: Path | None = None) -> dict:
    """Verify an archive in memory; never extract it or write any files.

    Supplying SHA256SUMS additionally checks the complete archive against that
    checksum file. Neither an unsigned manifest nor a checksum proves authorship.
    """
    archive = Path(archive)
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ReleaseError("Archive exceeds its size limit")
    with archive.open("rb") as handle:
        data = handle.read(MAX_ARCHIVE_BYTES + 1)
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ReleaseError("Archive exceeds its size limit")
    if checksums is not None:
        _verify_checksum(archive, data, Path(checksums))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            entries = package.infolist()
            if not entries or len(entries) > MAX_ENTRIES:
                raise ReleaseError("Archive has an invalid number of entries")
            seen = set()
            total = 0
            names = []
            for entry in entries:
                # ZipInfo normalizes backslashes on Windows and truncates NUL
                # bytes. Validate the original central-directory name first.
                _safe_name(entry.orig_filename)
                _safe_name(entry.filename)
                folded = entry.filename.casefold()
                if folded in seen:
                    raise ReleaseError("Archive contains duplicate or case-colliding paths")
                seen.add(folded)
                names.append(entry.filename)
                mode = entry.external_attr >> 16
                if entry.is_dir() or stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
                    raise ReleaseError("Archive must contain regular files only")
                if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                    raise ReleaseError("Archive contains a special file")
                if entry.flag_bits & 1:
                    raise ReleaseError("Encrypted release entries are not supported")
                if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ReleaseError("Unsupported release compression")
                if entry.file_size < 0 or entry.file_size > MAX_FILE_BYTES:
                    raise ReleaseError("Archive entry exceeds its size limit")
                total += entry.file_size
                if total > MAX_TOTAL_BYTES:
                    raise ReleaseError("Archive exceeds its total expanded size limit")
            for name in seen:
                parts = name.split("/")
                if any("/".join(parts[:index]) in seen for index in range(1, len(parts))):
                    raise ReleaseError("Archive contains a file/directory path collision")
            roots = {name.split("/", 1)[0] for name in names}
            if len(roots) != 1:
                raise ReleaseError("Archive must have one versioned root directory")
            prefix = next(iter(roots)) + "/"
            manifest_path = prefix + MANIFEST_NAME
            if manifest_path not in names:
                raise ReleaseError("Release manifest is missing")
            if package.getinfo(manifest_path).file_size > MAX_MANIFEST_BYTES:
                raise ReleaseError("Release manifest exceeds its size limit")
            manifest = _json(package.read(manifest_path))
            if set(manifest) != {"version", "files"} or not isinstance(manifest["version"], str):
                raise ReleaseError("Release manifest has an invalid schema")
            version = _version(manifest["version"].encode("utf-8"))
            if prefix != f"ascend-{version}/" or archive.name != f"ascend-{version}.zip":
                raise ReleaseError("Archive name, root directory, and version must agree")
            files = manifest["files"]
            if not isinstance(files, dict) or any(
                    not isinstance(name, str) or not isinstance(digest, str)
                    or HASH_RE.fullmatch(digest) is None for name, digest in files.items()):
                raise ReleaseError("Manifest files must map paths to SHA-256 hashes")
            allowed = set(REQUIRED_FILES) | set(OPTIONAL_FILES)
            if not set(REQUIRED_FILES).issubset(files) or not set(files).issubset(allowed):
                raise ReleaseError("Manifest is missing required assets or includes unsupported files")
            actual = {name[len(prefix):] for name in names if name != manifest_path}
            if set(files) != actual:
                raise ReleaseError("Manifest file set does not match the archive")
            version_data = None
            skill_data = None
            for relative, expected in files.items():
                # Size metadata was bounded above; bounded reading also guards
                # against inconsistent ZIP headers and unexpected decompression.
                with package.open(prefix + relative) as handle:
                    contents = handle.read(MAX_FILE_BYTES + 1)
                if len(contents) > MAX_FILE_BYTES or sha256(contents) != expected:
                    raise ReleaseError(f"Payload hash mismatch: {relative}")
                if relative == "VERSION":
                    version_data = contents
                if relative == "skills/ascend/SKILL.md":
                    skill_data = contents
            if _version(version_data) != version:
                raise ReleaseError("VERSION does not agree with the release manifest")
            _check_skill_version(skill_data, version)
            return manifest
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error) as error:
        raise ReleaseError("Invalid or unreadable release archive") from error


def _publish_immutable(outputs: dict[Path, bytes]) -> None:
    """Publish complete files atomically and never replace existing content."""
    for path, contents in outputs.items():
        if path.exists() and (not path.is_file() or path.read_bytes() != contents):
            raise ReleaseError(f"Refusing to overwrite different existing release content: {path.name}")
    parent = next(iter(outputs)).parent
    created = []
    with tempfile.TemporaryDirectory(prefix=".ascend-build-", dir=parent) as temporary:
        try:
            for index, (path, contents) in enumerate(outputs.items()):
                staged = Path(temporary) / str(index)
                staged.write_bytes(contents)
                try:
                    # Hard linking is atomic, and fails if a concurrent build
                    # already created the destination. No partial file is visible.
                    os.link(staged, path)
                    created.append(path)
                except FileExistsError:
                    if not path.is_file() or path.read_bytes() != contents:
                        raise ReleaseError(f"Release output already exists with different content: {path.name}")
        except BaseException:
            for path in reversed(created):
                path.unlink()
            raise


def build_release(source_root: Path, output_dir: Path) -> Path:
    """Build an allowlisted deterministic ZIP and two integrity sidecars."""
    source_root = Path(source_root).resolve()
    output_dir = Path(output_dir).resolve()
    payload = {name: _read_source(source_root, name) for name in REQUIRED_FILES}
    for name in OPTIONAL_FILES:
        if (source_root / name).exists():
            payload[name] = _read_source(source_root, name)
    if sum(map(len, payload.values())) > MAX_TOTAL_BYTES - MAX_MANIFEST_BYTES:
        raise ReleaseError("Release sources exceed the total size limit")
    version = _version(payload["VERSION"])
    _check_skill_version(payload["skills/ascend/SKILL.md"], version)
    manifest = {"version": version, "files": {name: sha256(payload[name]) for name in sorted(payload)}}
    manifest_data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    payload[MANIFEST_NAME] = manifest_data
    archive_name = f"ascend-{version}.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for name in sorted(payload):
            entry = zipfile.ZipInfo(f"ascend-{version}/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(entry, payload[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    archive_data = buffer.getvalue()
    checksum_data = f"{sha256(archive_data)}  {archive_name}\n".encode("ascii")
    output_dir.mkdir(parents=True, exist_ok=True)
    # Verify staged artifacts using exactly the verification consumers will run.
    with tempfile.TemporaryDirectory(prefix=".ascend-verify-", dir=output_dir) as temporary:
        staged_archive = Path(temporary) / archive_name
        staged_checksums = Path(temporary) / "SHA256SUMS"
        staged_archive.write_bytes(archive_data)
        staged_checksums.write_bytes(checksum_data)
        verify_release(staged_archive, staged_checksums)
    target = output_dir / archive_name
    _publish_immutable({target: archive_data, output_dir / "SHA256SUMS": checksum_data,
                        output_dir / MANIFEST_NAME: manifest_data})
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Build destination (default: source .local/dist)")
    parser.add_argument("--verify", type=Path, metavar="ARCHIVE", help="Verify a release without extracting")
    parser.add_argument("--checksums", type=Path, metavar="SHA256SUMS", help="Checksum file for --verify")
    arguments = parser.parse_args(argv)
    if arguments.verify and (arguments.output or not arguments.checksums):
        parser.error("--verify requires --checksums and cannot be combined with --output")
    if arguments.checksums and not arguments.verify:
        parser.error("--checksums requires --verify")
    try:
        if arguments.verify:
            manifest = verify_release(arguments.verify, arguments.checksums)
            print(f"Verified ASCEND {manifest['version']}: {len(manifest['files'])} payload files")
        else:
            archive = build_release(ROOT, arguments.output or ROOT / ".local/dist")
            print(f"Built {archive.name}; SHA256SUMS and release-manifest.json are alongside it")
    except (ReleaseError, OSError) as error:
        print(f"Release error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
