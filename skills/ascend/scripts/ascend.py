#!/usr/bin/env python3
"""ASCEND local evidence store. Standard library only; never calls a connector."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import http.server
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid
from urllib.parse import unquote, urlsplit


class AscendError(Exception):
    """A validation, integrity, authorization, or workspace error."""


ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
GENERATION = re.compile(r"g-[0-9]{6}-[a-f0-9]{16}\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z"
)
ASSETS = Path(__file__).resolve().parents[1] / "assets" / "dashboard"
ALLOWED_FILES = {"index.html", "styles.css", "app.js"}
DASHBOARD_MARKER = "<!-- ASCEND-GENERATED-DASHBOARD v1 -->"
MAX_INPUT_BYTES = 16 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise AscendError(message)


def fields(value, required, optional=(), where="object"):
    require(type(value) is dict, f"{where}: expected an object")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    require(not missing, f"{where}: missing fields {sorted(missing)}")
    require(not extra, f"{where}: unsupported fields {sorted(extra)}")


def string(value, where, *, empty=False):
    require(type(value) is str, f"{where}: expected a string")
    require(empty or bool(value.strip()), f"{where}: must not be empty")
    return value


def identifier(value, where):
    string(value, where)
    require(bool(ID.fullmatch(value)), f"{where}: invalid identifier")
    return value


def enum(value, choices, where):
    require(type(value) is str and value in choices, f"{where}: expected one of {sorted(choices)}")


def array(value, where):
    require(type(value) is list, f"{where}: expected an array")
    return value


def boolean(value, where):
    require(type(value) is bool, f"{where}: expected a boolean")


def finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def timestamp(value, where):
    string(value, where)
    require(bool(TIMESTAMP.fullmatch(value)), f"{where}: expected an ISO 8601 UTC timestamp")
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AscendError(f"{where}: invalid timestamp") from exc


def date(value, where):
    string(value, where)
    require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), f"{where}: expected YYYY-MM-DD")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise AscendError(f"{where}: invalid date") from exc


def refs(values, available, where):
    array(values, where)
    seen = set()
    for item in values:
        identifier(item, where)
        require(item in available, f"{where}: unknown reference {item}")
        require(item not in seen, f"{where}: duplicate reference {item}")
        seen.add(item)


def validate(data):
    """Validate supplied evidence structure, not its truth or real-world consent."""
    fields(data, ("schema_version", "captured_at", "project", "sources", "coverage", "metrics",
                  "findings", "benchmarks", "actions", "links"), where="snapshot")
    require(type(data["schema_version"]) is int and data["schema_version"] == 1,
            "schema_version: expected integer 1")
    captured_at = timestamp(data["captured_at"], "captured_at")
    project = data["project"]
    fields(project, ("id", "name", "domain", "summary", "objective", "constraints", "brand", "simulation"),
           where="project")
    identifier(project["id"], "project.id")
    for key in ("name", "domain", "summary", "objective"):
        string(project[key], f"project.{key}")
    for item in array(project["constraints"], "project.constraints"):
        string(item, "project.constraints[]")
    boolean(project["simulation"], "project.simulation")
    fields(project["brand"], ("accent",), where="project.brand")
    require(type(project["brand"]["accent"]) is str
            and bool(re.fullmatch(r"#[a-fA-F0-9]{6}", project["brand"]["accent"])),
            "project.brand.accent: expected a six-digit hex color")

    all_ids = {project["id"]}
    groups = {}
    for group in ("sources", "metrics", "findings", "benchmarks", "actions"):
        groups[group] = {}
        for item in array(data[group], group):
            require(type(item) is dict, f"{group}[]: expected an object")
            item_id = identifier(item.get("id"), f"{group}[].id")
            require(item_id not in all_ids, f"duplicate identifier: {item_id}")
            all_ids.add(item_id)
            groups[group][item_id] = item
    sources = groups["sources"]
    for source in sources.values():
        fields(source, ("id", "title", "kind", "locator", "captured_at", "status"), ("note",), "source")
        for key in ("title", "locator"):
            string(source[key], f"source.{key}")
        enum(source["kind"], {"provided", "connector", "file", "web", "simulation"}, "source.kind")
        enum(source["status"], {"available", "unavailable"}, "source.status")
        require(timestamp(source["captured_at"], "source.captured_at") <= captured_at,
                "source.captured_at: cannot be after the snapshot")
        if "note" in source:
            string(source["note"], "source.note", empty=True)

    def evidence(values, where, required=False):
        refs(values, sources, where)
        if required:
            require(any(sources[item]["status"] == "available" for item in values),
                    f"{where}: an available supporting source is required")

    areas = set()
    for item in array(data["coverage"], "coverage"):
        fields(item, ("area", "status", "source_ids", "note"), where="coverage[]")
        string(item["area"], "coverage.area")
        require(item["area"] not in areas, f"coverage: duplicate area {item['area']}")
        areas.add(item["area"])
        enum(item["status"], {"examined", "partial", "unavailable", "not_applicable"}, "coverage.status")
        evidence(item["source_ids"], "coverage.source_ids", item["status"] == "examined")
        string(item["note"], "coverage.note", empty=True)

    for metric in groups["metrics"].values():
        fields(metric, ("id", "label", "value", "unit", "period_start", "period_end", "source_ids",
                        "comparability_key"), where="metric")
        for key in ("label", "unit", "comparability_key"):
            string(metric[key], f"metric.{key}")
        value = metric["value"]
        require(value is None or finite_number(value),
                "metric.value: expected a finite number or null")
        start, end = date(metric["period_start"], "metric.period_start"), date(metric["period_end"], "metric.period_end")
        require(start <= end, "metric: period_start must be before or equal to period_end")
        require(end <= captured_at.date(), "metric.period_end: cannot be after the snapshot date")
        evidence(metric["source_ids"], "metric.source_ids", value is not None)

    for finding in groups["findings"].values():
        fields(finding, ("id", "title", "detail", "kind", "severity", "confidence", "source_ids",
                         "metric_ids", "verification"), where="finding")
        for key in ("title", "detail", "verification"):
            string(finding[key], f"finding.{key}")
        enum(finding["kind"], {"observed", "hypothesis", "unknown"}, "finding.kind")
        enum(finding["severity"], {"red", "yellow", "green", "grey"}, "finding.severity")
        enum(finding["confidence"], {"high", "medium", "low"}, "finding.confidence")
        require(finding["kind"] != "unknown" or finding["severity"] == "grey",
                "finding: unknown findings must use grey severity")
        evidence(finding["source_ids"], "finding.source_ids", finding["kind"] == "observed")
        refs(finding["metric_ids"], groups["metrics"], "finding.metric_ids")

    for benchmark in groups["benchmarks"].values():
        fields(benchmark, ("id", "label", "source_ids", "comparison", "limitations", "simulated"),
               where="benchmark")
        for key in ("label", "comparison", "limitations"):
            string(benchmark[key], f"benchmark.{key}")
        boolean(benchmark["simulated"], "benchmark.simulated")
        evidence(benchmark["source_ids"], "benchmark.source_ids", True)
        require(benchmark["simulated"] or not any(sources[x]["kind"] == "simulation" for x in benchmark["source_ids"]),
                "benchmark: simulation sources require simulated=true")

    for action in groups["actions"].values():
        fields(action, ("id", "title", "rationale", "finding_ids", "status", "cost", "expected_outcome",
                        "verification", "authorization"), where="action")
        for key in ("title", "rationale", "cost", "expected_outcome", "verification"):
            string(action[key], f"action.{key}")
        refs(action["finding_ids"], groups["findings"], "action.finding_ids")
        enum(action["status"], {"proposed", "authorized", "in_progress", "completed", "blocked", "cancelled"},
             "action.status")
        if action["authorization"] is not None:
            string(action["authorization"], "action.authorization")
        require(action["status"] not in {"authorized", "in_progress", "completed"}
                or bool(action["authorization"]), "action: this status requires an authorization reference")

    for link in array(data["links"], "links"):
        fields(link, ("from", "to", "relation"), where="link")
        refs([link["from"]], all_ids, "link.from")
        refs([link["to"]], all_ids, "link.to")
        string(link["relation"], "link.relation")
    # Compact input may expand substantially during canonical serialization.
    # Reject it here, before any workspace, lock, or staged file can be created.
    canonical(data)
    return data


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"JSON: duplicate field {key}")
        result[key] = value
    return result


def decode_json(raw, where="JSON"):
    require(len(raw) <= MAX_INPUT_BYTES, f"{where}: exceeds 16 MiB limit")
    try:
        return json.loads(raw, object_pairs_hook=_object_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(AscendError(f"JSON: invalid {value}")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise AscendError(f"{where}: invalid JSON ({exc})") from exc


def _regular(path):
    require(not _linked(path), f"refusing symbolic link or junction: {path.name}")
    require(path.is_file(), f"missing regular file: {path.name}")
    return path


def read_json(path):
    return decode_json(_regular(Path(path)).read_bytes(), str(path))


def canonical(data):
    raw = (json.dumps(data, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    require(len(raw) <= MAX_INPUT_BYTES, "canonical JSON: exceeds 16 MiB limit")
    return raw


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe_dir(path, *, must_exist=True):
    require(not _linked(path), f"refusing symbolic link or junction directory: {path.name}")
    require(not path.exists() or path.is_dir(), f"expected a directory: {path.name}")
    if must_exist:
        require(path.is_dir(), f"missing directory: {path.name}")
    return path


def _workspace(path, *, must_exist=True):
    # Inspect every existing component before resolving so a symlink is not hidden.
    path = Path(os.path.abspath(path))
    for component in (path, *path.parents):
        require(not _linked(component), f"refusing symbolic link or junction workspace component: {component.name}")
    return _safe_dir(path, must_exist=must_exist)


def _linked(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _assert_continuity(before, after):
    require(before["project"]["id"] == after["project"]["id"], "capture: project.id cannot change")
    require(before["project"]["simulation"] == after["project"]["simulation"],
            "capture: cannot mix simulated and real project histories")
    require(timestamp(after["captured_at"], "captured_at") > timestamp(before["captured_at"], "captured_at"),
            "capture: captured_at must strictly advance")


def load_state(workspace):
    """Read and verify the active generation and its complete manifest ancestry."""
    workspace = _workspace(workspace)
    store = _safe_dir(workspace / ".ascend")
    generations = _safe_dir(store / "generations")
    current = read_json(store / "CURRENT")
    fields(current, ("generation", "manifest_sha256"), where="CURRENT")
    require(type(current["generation"]) is str and GENERATION.fullmatch(current["generation"]),
            "CURRENT: invalid generation")
    require(type(current["manifest_sha256"]) is str and SHA256.fullmatch(current["manifest_sha256"]),
            "CURRENT: invalid digest")
    chain, seen = [], set()
    pointer = current
    while pointer is not None:
        generation_id = pointer["generation"]
        require(generation_id not in seen, "manifest: ancestry cycle")
        seen.add(generation_id)
        require(len(seen) <= 10000, "manifest: history exceeds 10000 captures")
        directory = _safe_dir(generations / generation_id)
        raw = _regular(directory / "manifest.json").read_bytes()
        require(digest(raw) == pointer["manifest_sha256"], "manifest: SHA256 mismatch")
        manifest = decode_json(raw, "manifest")
        fields(manifest, ("schema_version", "generation", "project_id", "actor", "parent", "snapshots"),
               where="manifest")
        require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1,
                "manifest: unsupported schema")
        require(manifest["generation"] == generation_id, "manifest: generation mismatch")
        identifier(manifest["project_id"], "manifest.project_id")
        string(manifest["actor"], "manifest.actor")
        entries = array(manifest["snapshots"], "manifest.snapshots")
        require(bool(entries), "manifest: empty snapshots")
        for entry in entries:
            fields(entry, ("id", "generation", "captured_at", "sha256", "previous_sha256"), where="snapshot entry")
            identifier(entry["id"], "snapshot entry.id")
            require(type(entry["generation"]) is str and GENERATION.fullmatch(entry["generation"]),
                    "snapshot entry: invalid generation")
            timestamp(entry["captured_at"], "snapshot entry.captured_at")
            for key in ("sha256", "previous_sha256"):
                require((key == "previous_sha256" and entry[key] is None)
                        or (type(entry[key]) is str and SHA256.fullmatch(entry[key])),
                        f"snapshot entry: invalid {key}")
        if manifest["parent"] is not None:
            fields(manifest["parent"], ("generation", "manifest_sha256"), where="manifest.parent")
            require(type(manifest["parent"]["generation"]) is str
                    and GENERATION.fullmatch(manifest["parent"]["generation"]), "manifest.parent: invalid generation")
            require(type(manifest["parent"]["manifest_sha256"]) is str
                    and SHA256.fullmatch(manifest["parent"]["manifest_sha256"]), "manifest.parent: invalid digest")
        chain.append((manifest, pointer["manifest_sha256"]))
        pointer = manifest["parent"]
    chain.reverse()
    snapshots, ids, previous_manifest, previous_sha = [], set(), None, None
    for manifest, manifest_sha in chain:
        entries = manifest["snapshots"]
        if previous_manifest is None:
            require(len(entries) == 1, "manifest: baseline must contain exactly one snapshot")
        else:
            require(manifest["project_id"] == previous_manifest["project_id"], "manifest: project changed")
            require(len(entries) == len(previous_manifest["snapshots"]) + 1
                    and entries[:-1] == previous_manifest["snapshots"], "manifest: historical entries changed")
        entry = entries[-1]
        require(entry["generation"] == manifest["generation"], "manifest: snapshot generation mismatch")
        require(entry["id"] not in ids, "manifest: duplicate snapshot id")
        ids.add(entry["id"])
        require(entry["previous_sha256"] == previous_sha, "snapshot: digest chain mismatch")
        raw = _regular(generations / entry["generation"] / "snapshot.json").read_bytes()
        require(digest(raw) == entry["sha256"], "snapshot: SHA256 mismatch")
        snapshot = validate(decode_json(raw, "snapshot"))
        require(snapshot["captured_at"] == entry["captured_at"], "snapshot: captured_at mismatch")
        require(snapshot["project"]["id"] == manifest["project_id"], "snapshot: project mismatch")
        if snapshots:
            _assert_continuity(snapshots[-1], snapshot)
        snapshots.append(snapshot)
        previous_sha = entry["sha256"]
        previous_manifest = manifest
    return {"workspace": workspace, "pointer": current, "manifest": chain[-1][0], "history": snapshots}


@contextlib.contextmanager
def writer_lock(workspace):
    lock = workspace / ".ascend.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise AscendError("workspace is locked by another writer; inspect .ascend.lock before manual recovery") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(f"pid={os.getpid()}\n")
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        lock.unlink()


def _write_new(path, raw):
    with open(path, "xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _prepare_capture(data, actor, previous=None):
    """Prepare every bounded serialized artifact without any filesystem writes."""
    sequence = len(previous["history"]) + 1 if previous else 1
    require(sequence <= 10000, "history exceeds 10000 captures")
    generation = f"g-{sequence:06d}-{uuid.uuid4().hex[:16]}"
    snapshot_id = f"capture-{sequence:06d}-{uuid.uuid4().hex[:16]}"
    raw_snapshot = canonical(data)
    old_entries = previous["manifest"]["snapshots"] if previous else []
    entry = {"id": snapshot_id, "generation": generation, "captured_at": data["captured_at"],
             "sha256": digest(raw_snapshot), "previous_sha256": old_entries[-1]["sha256"] if old_entries else None}
    manifest = {"schema_version": 1, "generation": generation, "project_id": data["project"]["id"],
                "actor": actor, "parent": previous["pointer"] if previous else None,
                "snapshots": old_entries + [entry]}
    raw_manifest = canonical(manifest)
    pointer = {"generation": generation, "manifest_sha256": digest(raw_manifest)}
    return {"entry": entry, "generation": generation, "snapshot": raw_snapshot,
            "manifest": raw_manifest, "pointer": canonical(pointer)}


def _commit_capture(store, prepared):
    generations = store / "generations"
    generation = prepared["generation"]
    stage = Path(tempfile.mkdtemp(prefix=".pending-", dir=generations))
    destination = generations / generation
    pointer_temp = store / f".CURRENT-{uuid.uuid4().hex}.tmp"
    committed = False
    try:
        _write_new(stage / "snapshot.json", prepared["snapshot"])
        _write_new(stage / "manifest.json", prepared["manifest"])
        stage.rename(destination)
        _write_new(pointer_temp, prepared["pointer"])
        os.replace(pointer_temp, store / "CURRENT")
        committed = True
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if pointer_temp.exists():
            pointer_temp.unlink()
        if not committed and destination.exists():
            shutil.rmtree(destination)
    return prepared["entry"]


def _authorized(authorized):
    require(authorized is True, "write authorization acknowledgement required: --authorize-write")


def initialize(data, workspace, actor, *, authorized=False):
    validate(data)
    string(actor, "actor")
    _authorized(authorized)
    workspace = _workspace(workspace, must_exist=False)
    # Workspace parents must already exist; ASCEND creates only the named leaf.
    require(workspace.parent.is_dir(), "workspace parent must exist")
    prepared = _prepare_capture(data, actor)
    created_workspace = not workspace.exists()
    workspace.mkdir(exist_ok=True)
    try:
        with writer_lock(workspace):
            store = workspace / ".ascend"
            require(not store.exists() and not _linked(store), "workspace is already initialized or contains .ascend")
            stage = Path(tempfile.mkdtemp(prefix=".ascend-init-", dir=workspace))
            try:
                (stage / "generations").mkdir()
                entry = _commit_capture(stage, prepared)
                stage.rename(store)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        return entry
    except Exception:
        if created_workspace:
            try:
                workspace.rmdir()
            except OSError:
                pass
        raise


def capture(data, workspace, actor, *, authorized=False):
    validate(data)
    string(actor, "actor")
    _authorized(authorized)
    previous = load_state(workspace)
    _assert_continuity(previous["history"][-1], data)
    prepared = _prepare_capture(data, actor, previous)
    workspace = previous["workspace"]
    with writer_lock(workspace):
        # Do not rebase a prepared capture: artifact size and ancestry were checked
        # before taking the lock. A changed base needs a new explicit invocation.
        latest = load_state(workspace)
        require(latest["pointer"] == previous["pointer"], "workspace changed during capture; run capture again")
        return _commit_capture(workspace / ".ascend", prepared)


def metric_changes(before, after):
    old = {m["id"]: m for m in before["metrics"]}
    new = {m["id"]: m for m in after["metrics"]}
    result = []
    for metric_id in dict.fromkeys([*old, *new]):
        left, right = old.get(metric_id), new.get(metric_id)
        comparable, reason, delta = True, "Same unit, definition, and inclusive period duration.", None
        if left is None or right is None:
            comparable, reason = False, "Metric is missing from one snapshot."
        elif left["value"] is None or right["value"] is None:
            comparable, reason = False, "Metric value is unavailable in one snapshot."
        elif left["unit"] != right["unit"]:
            comparable, reason = False, "Metric units differ."
        elif left["comparability_key"] != right["comparability_key"]:
            comparable, reason = False, "Metric definition or measurement scope differs."
        else:
            left_days = (date(left["period_end"], "period_end") - date(left["period_start"], "period_start")).days + 1
            right_days = (date(right["period_end"], "period_end") - date(right["period_start"], "period_start")).days + 1
            if left_days != right_days:
                comparable, reason = False, "Inclusive measurement period durations differ."
            else:
                delta = right["value"] - left["value"]
                if not finite_number(delta):
                    comparable, reason, delta = False, "Difference exceeds the supported numeric range.", None
        result.append({"metric_id": metric_id, "label": (right or left)["label"],
                       "before": left["value"] if left else None, "after": right["value"] if right else None,
                       "delta": delta, "comparable": comparable, "reason": reason})
    return result


def export_payload(state):
    history = state["history"]
    return {"current": history[-1], "history": history, "baseline": history[0],
            "changes": metric_changes(history[0], history[-1]),
            "snapshots": [{key: entry[key] for key in ("id", "captured_at", "sha256")}
                          for entry in state["manifest"]["snapshots"]],
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")}


def html_safe_json(data):
    raw = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return raw.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace(
        "\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _owned_dashboard_index(dashboard):
    require((dashboard / "index.html").exists(),
            "dashboard is not owned by ASCEND; existing files were preserved")
    _regular(dashboard / "index.html")
    marker = (DASHBOARD_MARKER + "\n").encode("utf-8")
    with open(dashboard / "index.html", "rb") as stream:
        require(stream.read(len(marker)) == marker,
                "dashboard is not owned by ASCEND; existing files were preserved")


def _dashboard_directory(dashboard, *, allow_empty=False):
    """Recognize our generated output without claiming arbitrary HTML as ours."""
    _safe_dir(dashboard)
    existing = set(p.name for p in dashboard.iterdir())
    require(existing <= ALLOWED_FILES, "dashboard contains unrelated files; choose a clean workspace")
    for item in dashboard.iterdir():
        _regular(item)
    if not existing and allow_empty:
        return
    _owned_dashboard_index(dashboard)


def render(workspace, *, authorized=False, assets=None):
    _authorized(authorized)
    state = load_state(workspace)
    assets = _safe_dir(Path(assets) if assets else ASSETS)
    template = _regular(assets / "template.html").read_text(encoding="utf-8")
    marker = "{{ASCEND_DATA}}"
    require(template.count(marker) == 1, "dashboard template must contain exactly one {{ASCEND_DATA}} marker")
    # Marker stands for the complete data script, not an interpolated JavaScript expression.
    block = '<script type="application/json" id="ascend-data">' + html_safe_json(export_payload(state)) + "</script>"
    html = DASHBOARD_MARKER + "\n" + template.replace(marker, block)
    content = {"index.html": html.encode("utf-8")}
    for name in ("styles.css", "app.js"):
        content[name] = _regular(assets / name).read_bytes()
    workspace = state["workspace"]
    dashboard = workspace / "dashboard"
    _safe_dir(dashboard, must_exist=False)
    if dashboard.exists():
        _dashboard_directory(dashboard, allow_empty=True)
    with writer_lock(workspace):
        # Abort if a capture changed while preparing the render.
        latest = load_state(workspace)
        require(latest["pointer"] == state["pointer"], "workspace changed during render; run render again")
        if dashboard.exists():
            _dashboard_directory(dashboard, allow_empty=True)
        stage = Path(tempfile.mkdtemp(prefix=".dashboard-", dir=workspace))
        backup = workspace / f".dashboard-backup-{uuid.uuid4().hex}"
        moved_old, committed = False, False
        try:
            for name, raw in content.items():
                _write_new(stage / name, raw)
            if dashboard.exists():
                dashboard.rename(backup)
                moved_old = True
            stage.rename(dashboard)
            committed = True
        finally:
            if not committed and moved_old:
                backup.rename(dashboard)
            if stage.exists():
                shutil.rmtree(stage)
            if committed and backup.exists():
                shutil.rmtree(backup)
    return dashboard / "index.html"


def make_server(workspace, port=8765):
    require(type(port) is int and 0 <= port <= 65535, "port must be between 0 and 65535")
    workspace = _workspace(workspace)
    load_state(workspace)
    dashboard = _safe_dir(workspace / "dashboard")
    _owned_dashboard_index(dashboard)

    class DashboardHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self._respond(False)

        def do_HEAD(self):
            self._respond(True)

        def _respond(self, head_only):
            # Reject other Host names to prevent a DNS-rebinding origin from reading local reports.
            allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host", "").lower() not in allowed_hosts:
                self.send_error(403)
                return
            path = unquote(urlsplit(self.path).path)
            name = "index.html" if path == "/" else path.removeprefix("/")
            if name not in ALLOWED_FILES or path not in {"/", "/" + name}:
                self.send_error(404)
                return
            try:
                _safe_dir(dashboard)
                raw = _regular(dashboard / name).read_bytes()
            except (AscendError, OSError):
                self.send_error(404)
                return
            self.send_response(200)
            mime = {"index.html": "text/html", "styles.css": "text/css", "app.js": "application/javascript"}[name]
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; "
                             "img-src 'self' data:; connect-src 'none'; font-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            if not head_only:
                self.wfile.write(raw)

        def log_message(self, fmt, *args):
            # Standard HTTP access logging omits query strings that can contain private data.
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    server.daemon_threads = True
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate", help="Read-only validation of a supplied snapshot")
    check.add_argument("input")
    for name in ("init", "capture"):
        command = sub.add_parser(name)
        command.add_argument("input")
        command.add_argument("--workspace", required=True)
        command.add_argument("--actor", required=True)
        command.add_argument("--authorize-write", action="store_true")
    verify = sub.add_parser("verify", help="Read-only verification of all stored captures")
    verify.add_argument("--workspace", required=True)
    report = sub.add_parser("render")
    report.add_argument("--workspace", required=True)
    report.add_argument("--authorize-write", action="store_true")
    serve = sub.add_parser("serve")
    serve.add_argument("--workspace", required=True)
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            validate(read_json(args.input))
            print("Snapshot structure and references are valid; truth and consent are not certified.")
        elif args.command in {"init", "capture"}:
            data = read_json(args.input)
            operation = initialize if args.command == "init" else capture
            entry = operation(data, args.workspace, args.actor, authorized=args.authorize_write)
            print(f"Stored {entry['id']} SHA256 {entry['sha256']}")
        elif args.command == "verify":
            state = load_state(args.workspace)
            print(f"Verified {len(state['history'])} capture(s), including manifest ancestry and snapshot digests.")
        elif args.command == "render":
            print(render(args.workspace, authorized=args.authorize_write))
        elif args.command == "serve":
            with make_server(args.workspace, args.port) as server:
                print(f"ASCEND local dashboard: http://127.0.0.1:{server.server_port}/", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        return 0
    except (AscendError, OSError, ValueError, OverflowError, RecursionError) as exc:
        print(f"ASCEND error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
