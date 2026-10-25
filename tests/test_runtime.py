"""Behavioral tests for evidence validation, transaction safety, and local isolation."""

from concurrent.futures import ThreadPoolExecutor
import copy
import http.client
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "ascend" / "scripts" / "ascend.py"
SPEC = importlib.util.spec_from_file_location("ascend_runtime", SCRIPT)
ascend = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ascend)


def snapshot(*, followup=False):
    """Independent minimal evidence fixture, not the dashboard demonstration."""
    return {
        "schema_version": 1,
        "captured_at": "2026-10-25T12:00:00Z" if followup else "2026-10-18T12:00:00Z",
        "project": {"id": "test-project", "name": "Test project", "domain": "education",
                    "summary": "Synthetic evidence for runtime tests.", "objective": "Complete a working page.",
                    "constraints": ["One hour per day"], "brand": {"accent": "#8ada71"}, "simulation": True},
        "sources": [{"id": "source-notes", "title": "Simulated lesson log", "kind": "simulation",
                     "locator": "simulation://lesson-log", "captured_at": "2026-10-18T11:00:00Z",
                     "status": "available"}],
        "coverage": [{"area": "Learning outcomes", "status": "examined", "source_ids": ["source-notes"],
                      "note": "Only the lesson log was examined."}],
        "metrics": [{"id": "metric-lessons", "label": "Lessons completed", "value": 3 if followup else 0,
                     "unit": "lessons", "period_start": "2026-10-19" if followup else "2026-10-12",
                     "period_end": "2026-10-25" if followup else "2026-10-18",
                     "source_ids": ["source-notes"], "comparability_key": "lessons:v1:7days"}],
        "findings": [{"id": "finding-practice", "title": "Practice time is limited", "detail": "The lesson log lists time constraints.",
                      "kind": "observed", "severity": "yellow", "confidence": "medium", "source_ids": ["source-notes"],
                      "metric_ids": ["metric-lessons"], "verification": "Review a future lesson log."}],
        "benchmarks": [{"id": "benchmark-routine", "label": "Synthetic reference routine", "source_ids": ["source-notes"],
                        "comparison": "A fictional routine reserves time for practice.", "limitations": "Not real research.",
                        "simulated": True}],
        "actions": [{"id": "action-practice", "title": "Draft a practice routine", "rationale": "Time is constrained.",
                     "finding_ids": ["finding-practice"], "status": "proposed", "cost": "No spend; 20 minutes",
                     "expected_outcome": "A routine the learner can review.", "verification": "Ask the learner to review the draft.",
                     "authorization": None}],
        "links": [{"from": "finding-practice", "to": "action-practice", "relation": "motivates"}],
    }


def tree_bytes(path):
    return {str(item.relative_to(path)): item.read_bytes() for item in path.rglob("*") if item.is_file()}


class ValidationTests(unittest.TestCase):
    def test_valid_minimal_snapshot_and_utc_offset(self):
        data = snapshot()
        self.assertIs(ascend.validate(data), data)
        data["captured_at"] = "2026-10-18T12:00:00+00:00"
        ascend.validate(data)

    def test_empty_evidence_is_allowed_only_as_an_explicit_gap(self):
        data = snapshot()
        for key in ("sources", "coverage", "metrics", "findings", "benchmarks", "actions", "links"):
            data[key] = []
        ascend.validate(data)

    def test_required_types_dates_enums_and_references_reject_mutations(self):
        mutations = [
            ("schema bool", lambda d: d.update(schema_version=True)),
            ("extra field", lambda d: d.update(execute="dangerous instruction")),
            ("timestamp naive", lambda d: d.update(captured_at="2026-10-18T12:00:00")),
            ("timestamp offset", lambda d: d.update(captured_at="2026-10-18T12:00:00+01:00")),
            ("impossible date", lambda d: d.update(captured_at="2026-02-30T12:00:00Z")),
            ("project color", lambda d: d["project"]["brand"].update(accent="red; background:url(x)")),
            ("project simulation", lambda d: d["project"].update(simulation="true")),
            ("source duplicate", lambda d: d["sources"].append(copy.deepcopy(d["sources"][0]))),
            ("cross type duplicate", lambda d: d["metrics"][0].update(id="source-notes")),
            ("project duplicate", lambda d: d["sources"][0].update(id="test-project")),
            ("id path", lambda d: d["sources"][0].update(id="../secret")),
            ("source future", lambda d: d["sources"][0].update(captured_at="2026-10-19T12:00:00Z")),
            ("source unknown kind", lambda d: d["sources"][0].update(kind="guessed")),
            ("coverage unknown ref", lambda d: d["coverage"][0].update(source_ids=["missing"])),
            ("coverage duplicate area", lambda d: d["coverage"].append(copy.deepcopy(d["coverage"][0]))),
            ("coverage unsupported", lambda d: d["coverage"][0].update(source_ids=[])),
            ("metric boolean", lambda d: d["metrics"][0].update(value=True)),
            ("metric NaN", lambda d: d["metrics"][0].update(value=float("nan"))),
            ("metric infinity", lambda d: d["metrics"][0].update(value=float("inf"))),
            ("metric enormous integer", lambda d: d["metrics"][0].update(value=10**400)),
            ("metric unsupported", lambda d: d["metrics"][0].update(source_ids=[])),
            ("metric reversed dates", lambda d: d["metrics"][0].update(period_start="2026-10-19")),
            ("metric future", lambda d: d["metrics"][0].update(period_end="2026-10-19")),
            ("metric invalid date", lambda d: d["metrics"][0].update(period_start="2026-02-30")),
            ("finding unknown metric", lambda d: d["findings"][0].update(metric_ids=["missing"])),
            ("finding missing evidence", lambda d: d["findings"][0].update(source_ids=[])),
            ("finding unknown severity", lambda d: d["findings"][0].update(severity="purple")),
            ("finding unknown red", lambda d: d["findings"][0].update(kind="unknown", severity="red")),
            ("benchmark evidence", lambda d: d["benchmarks"][0].update(source_ids=[])),
            ("benchmark mislabelled simulation", lambda d: d["benchmarks"][0].update(simulated=False)),
            ("action unknown finding", lambda d: d["actions"][0].update(finding_ids=["missing"])),
            ("action completed no consent", lambda d: d["actions"][0].update(status="completed")),
            ("action authorized no consent", lambda d: d["actions"][0].update(status="authorized")),
            ("action running no consent", lambda d: d["actions"][0].update(status="in_progress")),
            ("action empty consent", lambda d: d["actions"][0].update(authorization=" ")),
            ("link unknown target", lambda d: d["links"][0].update(to="missing")),
            ("link unsupported relation", lambda d: d["links"][0].update(relation=None)),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                data = snapshot()
                mutate(data)
                with self.assertRaises(ascend.AscendError):
                    ascend.validate(data)

    def test_unavailable_source_cannot_support_observed_finding(self):
        data = snapshot()
        data["sources"][0]["status"] = "unavailable"
        data["coverage"][0]["status"] = "unavailable"
        data["metrics"][0]["value"] = None
        data["benchmarks"] = []
        with self.assertRaisesRegex(ascend.AscendError, "available supporting source"):
            ascend.validate(data)
        data["findings"][0].update(kind="unknown", severity="grey")
        ascend.validate(data)

    def test_declared_completion_needs_reference_and_is_not_executed(self):
        data = snapshot()
        data["actions"][0].update(status="completed", authorization="User approved a draft in test-session.")
        ascend.validate(data)
        self.assertEqual(data["actions"][0]["status"], "completed")

    def test_duplicate_json_keys_nonfinite_and_oversize_fail(self):
        for raw in (b'{"a":1,"a":2}', b'{"value":NaN}', b'{"value":Infinity}', b"{broken", b"\xff"):
            with self.subTest(raw=raw), self.assertRaises(ascend.AscendError):
                ascend.decode_json(raw)
        with mock.patch.object(ascend, "MAX_INPUT_BYTES", 5):
            with self.assertRaisesRegex(ascend.AscendError, "limit"):
                ascend.decode_json(b'{"long":1}')


class WorkspaceCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "project"

    def initialize(self):
        return ascend.initialize(snapshot(), self.workspace, "Claude Code test", authorized=True)


class StoreTests(WorkspaceCase):
    def test_initialize_and_capture_keep_baseline_and_digest_chain(self):
        baseline_entry = self.initialize()
        baseline_path = self.workspace / ".ascend" / "generations" / baseline_entry["generation"] / "snapshot.json"
        raw_before = baseline_path.read_bytes()
        entry = ascend.capture(snapshot(followup=True), self.workspace, "Codex test", authorized=True)
        state = ascend.load_state(self.workspace)
        self.assertEqual(len(state["history"]), 2)
        self.assertEqual(baseline_path.read_bytes(), raw_before)
        self.assertEqual(entry["previous_sha256"], baseline_entry["sha256"])
        self.assertEqual(state["manifest"]["actor"], "Codex test")
        self.assertEqual(state["history"][0]["metrics"][0]["value"], 0)
        self.assertEqual(state["history"][1]["metrics"][0]["value"], 3)
        self.assertEqual(state["history"][1]["actions"][0]["status"], "proposed")

    def test_init_preserves_existing_project_files(self):
        self.workspace.mkdir()
        existing = self.workspace / "project-source.txt"
        existing.write_bytes(b"keep exactly")
        self.initialize()
        self.assertEqual(existing.read_bytes(), b"keep exactly")

    def test_missing_authorization_creates_nothing(self):
        with self.assertRaisesRegex(ascend.AscendError, "authorization"):
            ascend.initialize(snapshot(), self.workspace, "test")
        self.assertFalse(self.workspace.exists())
        self.initialize()
        before = tree_bytes(self.workspace)
        with self.assertRaises(ascend.AscendError):
            ascend.capture(snapshot(followup=True), self.workspace, "test")
        with self.assertRaises(ascend.AscendError):
            ascend.render(self.workspace)
        self.assertEqual(tree_bytes(self.workspace), before)

    def test_invalid_input_creates_nothing_even_with_authorization(self):
        data = snapshot()
        data["metrics"][0]["value"] = False
        with self.assertRaises(ascend.AscendError):
            ascend.initialize(data, self.workspace, "test", authorized=True)
        self.assertFalse(self.workspace.exists())

    def test_compact_input_that_expands_beyond_storage_limit_creates_nothing(self):
        data = snapshot()
        data["project"]["constraints"] = ["x"] * 1_600_000
        compact = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.assertLess(len(compact), ascend.MAX_INPUT_BYTES)
        self.assertIsInstance(ascend.decode_json(compact), dict)
        with mock.patch.object(ascend, "writer_lock", side_effect=AssertionError("must not acquire a lock")):
            with self.assertRaisesRegex(ascend.AscendError, "canonical JSON.*limit"):
                ascend.initialize(data, self.workspace, "test", authorized=True)
        self.assertFalse(self.workspace.exists())

    def test_oversized_manifest_fails_before_init_or_capture_writes(self):
        self.initialize()
        before = tree_bytes(self.workspace)
        limit = len(ascend.canonical(snapshot(followup=True))) + 512
        with mock.patch.object(ascend, "MAX_INPUT_BYTES", limit):
            with mock.patch.object(ascend, "writer_lock", side_effect=AssertionError("must not acquire a lock")):
                with self.assertRaisesRegex(ascend.AscendError, "canonical JSON.*limit"):
                    ascend.capture(snapshot(followup=True), self.workspace, "x" * limit, authorized=True)
                new_workspace = self.root / "new-project"
                with self.assertRaisesRegex(ascend.AscendError, "canonical JSON.*limit"):
                    ascend.initialize(snapshot(), new_workspace, "x" * limit, authorized=True)
        self.assertEqual(tree_bytes(self.workspace), before)
        self.assertFalse(new_workspace.exists())

    def test_initialized_workspace_is_never_overwritten(self):
        self.initialize()
        before = tree_bytes(self.workspace)
        with self.assertRaisesRegex(ascend.AscendError, "already initialized"):
            self.initialize()
        self.assertEqual(tree_bytes(self.workspace), before)

    def test_invalid_continuity_does_not_write(self):
        self.initialize()
        before = tree_bytes(self.workspace)
        for change in (lambda d: d["project"].update(id="another-project"),
                       lambda d: d["project"].update(simulation=False),
                       lambda d: d.update(captured_at="2026-10-18T12:00:00Z")):
            with self.subTest(change=change):
                data = snapshot(followup=True)
                change(data)
                if data["captured_at"] == "2026-10-18T12:00:00Z":
                    data["metrics"][0].update(period_start="2026-10-12", period_end="2026-10-18")
                with self.assertRaises(ascend.AscendError):
                    ascend.capture(data, self.workspace, "test", authorized=True)
                self.assertEqual(tree_bytes(self.workspace), before)

    def test_writer_lock_blocks_capture_without_mutating_history(self):
        self.initialize()
        before = tree_bytes(self.workspace)
        with ascend.writer_lock(self.workspace):
            with self.assertRaisesRegex(ascend.AscendError, "locked"):
                ascend.capture(snapshot(followup=True), self.workspace, "test", authorized=True)
        self.assertEqual(tree_bytes(self.workspace), before)

    def test_simultaneous_writers_cannot_replace_each_other(self):
        self.initialize()
        gate = threading.Barrier(2)

        def attempt(actor):
            gate.wait(timeout=5)
            try:
                ascend.capture(snapshot(followup=True), self.workspace, actor, authorized=True)
                return "stored"
            except ascend.AscendError:
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, ["Claude Code", "Codex"]))
        self.assertEqual(sorted(results), ["rejected", "stored"])
        self.assertEqual(len(ascend.load_state(self.workspace)["history"]), 2)
        self.assertFalse((self.workspace / ".ascend.lock").exists())

    def test_capture_pointer_failure_rolls_back_all_new_files(self):
        self.initialize()
        before = tree_bytes(self.workspace)
        with mock.patch.object(ascend.os, "replace", side_effect=OSError("injected pointer failure")):
            with self.assertRaisesRegex(OSError, "injected"):
                ascend.capture(snapshot(followup=True), self.workspace, "test", authorized=True)
        self.assertEqual(tree_bytes(self.workspace), before)
        self.assertEqual(len(ascend.load_state(self.workspace)["history"]), 1)
        self.assertFalse((self.workspace / ".ascend.lock").exists())

    def test_init_failure_rolls_back_created_workspace(self):
        with mock.patch.object(ascend.os, "replace", side_effect=OSError("injected pointer failure")):
            with self.assertRaises(OSError):
                self.initialize()
        self.assertFalse(self.workspace.exists())

    def test_snapshot_tampering_stops_verify_capture_and_render(self):
        entry = self.initialize()
        path = self.workspace / ".ascend" / "generations" / entry["generation"] / "snapshot.json"
        path.write_bytes(path.read_bytes().replace(b"Test project", b"Fake project"))
        before = tree_bytes(self.workspace)
        for operation in (lambda: ascend.load_state(self.workspace),
                          lambda: ascend.capture(snapshot(followup=True), self.workspace, "test", authorized=True),
                          lambda: ascend.render(self.workspace, authorized=True)):
            with self.assertRaisesRegex(ascend.AscendError, "SHA256 mismatch"):
                operation()
        self.assertEqual(tree_bytes(self.workspace), before)

    def test_manifest_tampering_is_detected(self):
        entry = self.initialize()
        path = self.workspace / ".ascend" / "generations" / entry["generation"] / "manifest.json"
        path.write_bytes(path.read_bytes().replace(b"Claude Code test", b"different actor"))
        with self.assertRaisesRegex(ascend.AscendError, "SHA256 mismatch"):
            ascend.load_state(self.workspace)

    def test_historical_manifest_tampering_is_detected_after_capture(self):
        entry = self.initialize()
        ascend.capture(snapshot(followup=True), self.workspace, "test", authorized=True)
        path = self.workspace / ".ascend" / "generations" / entry["generation"] / "manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ascend.AscendError, "SHA256 mismatch"):
            ascend.load_state(self.workspace)

    def test_current_path_traversal_and_invalid_digest_are_rejected(self):
        self.initialize()
        current = self.workspace / ".ascend" / "CURRENT"
        for pointer in ({"generation": "../../private", "manifest_sha256": "a" * 64},
                        {"generation": "g-000001-" + "a" * 16, "manifest_sha256": "invalid"}):
            current.write_bytes(ascend.canonical(pointer))
            with self.assertRaises(ascend.AscendError):
                ascend.load_state(self.workspace)

    def test_symlink_workspaces_are_rejected_when_supported(self):
        real = self.root / "real"
        real.mkdir()
        link = self.root / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Symbolic link creation unavailable: {exc}")
        with self.assertRaisesRegex(ascend.AscendError, "symbolic link"):
            ascend.initialize(snapshot(), link, "test", authorized=True)
        self.assertEqual(list(real.iterdir()), [])


class ComparisonTests(unittest.TestCase):
    def test_zero_baseline_uses_absolute_delta_without_percentage(self):
        changes = ascend.metric_changes(snapshot(), snapshot(followup=True))
        self.assertEqual(changes[0]["delta"], 3)
        self.assertTrue(changes[0]["comparable"])
        self.assertNotIn("percent", json.dumps(changes))

    def test_incomparable_data_never_emits_numeric_delta(self):
        for name, mutate in (
            ("missing", lambda d: d.update(metrics=[])),
            ("unknown value", lambda d: d["metrics"][0].update(value=None)),
            ("unit", lambda d: d["metrics"][0].update(unit="minutes")),
            ("scope", lambda d: d["metrics"][0].update(comparability_key="other:v2")),
            ("period length", lambda d: d["metrics"][0].update(period_start="2026-10-20")),
        ):
            with self.subTest(name=name):
                after = snapshot(followup=True)
                mutate(after)
                change = ascend.metric_changes(snapshot(), after)[0]
                self.assertFalse(change["comparable"])
                self.assertIsNone(change["delta"])
                self.assertTrue(change["reason"])

    def test_new_metric_is_present_but_incomparable(self):
        before, after = snapshot(), snapshot(followup=True)
        after["metrics"].append(dict(after["metrics"][0], id="metric-new"))
        change = ascend.metric_changes(before, after)[1]
        self.assertEqual(change["metric_id"], "metric-new")
        self.assertFalse(change["comparable"])

    def test_overflowing_difference_is_incomparable(self):
        before, after = snapshot(), snapshot(followup=True)
        before["metrics"][0]["value"] = -1e308
        after["metrics"][0]["value"] = 1e308
        change = ascend.metric_changes(before, after)[0]
        self.assertFalse(change["comparable"])
        self.assertIsNone(change["delta"])


class DashboardTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.assets = self.root / "assets"
        self.assets.mkdir()
        (self.assets / "template.html").write_text(
            '<!doctype html><html><body><main id="app"></main>{{ASCEND_DATA}}<script src="app.js" defer></script></body></html>',
            encoding="utf-8")
        (self.assets / "styles.css").write_text("body { color: white; }", encoding="utf-8")
        (self.assets / "app.js").write_text("'use strict';", encoding="utf-8")

    def test_render_roundtrips_html_safe_payload_and_history(self):
        data = snapshot()
        attack = '</script><img src=x onerror="alert(1)"><script>bad()</script>&\u2028\u2029'
        data["project"]["name"] = attack
        ascend.initialize(data, self.workspace, "test", authorized=True)
        ascend.capture(snapshot(followup=True), self.workspace, "test", authorized=True)
        path = ascend.render(self.workspace, authorized=True, assets=self.assets)
        html = path.read_text(encoding="utf-8")
        self.assertNotIn('<img src=x', html)
        self.assertNotIn("<script>bad()", html)
        marker = '<script type="application/json" id="ascend-data">'
        payload = json.loads(html.split(marker)[1].split("</script>")[0])
        self.assertEqual(payload["baseline"]["project"]["name"], attack)
        self.assertEqual(len(payload["history"]), 2)
        self.assertEqual(payload["changes"][0]["delta"], 3)
        self.assertEqual(set(payload), {"current", "baseline", "history", "changes", "snapshots", "generated_at"})

    def test_render_refuses_to_overwrite_unrelated_dashboard_files(self):
        self.initialize()
        dashboard = self.workspace / "dashboard"
        dashboard.mkdir()
        (dashboard / "private.txt").write_text("keep", encoding="utf-8")
        before = tree_bytes(self.workspace)
        with self.assertRaisesRegex(ascend.AscendError, "unrelated"):
            ascend.render(self.workspace, authorized=True, assets=self.assets)
        self.assertEqual(tree_bytes(self.workspace), before)

    def test_preexisting_allowlisted_dashboard_files_are_preserved(self):
        self.workspace.mkdir()
        dashboard = self.workspace / "dashboard"
        dashboard.mkdir()
        originals = {"index.html": b"<!doctype html><title>User dashboard</title>",
                     "styles.css": b"/* User styles */", "app.js": b"// User application"}
        for name, raw in originals.items():
            (dashboard / name).write_bytes(raw)
        self.initialize()
        before = tree_bytes(self.workspace)
        with mock.patch.object(ascend, "writer_lock", side_effect=AssertionError("must not acquire a lock")):
            with self.assertRaisesRegex(ascend.AscendError, "not owned by ASCEND"):
                ascend.render(self.workspace, authorized=True, assets=self.assets)
        with self.assertRaisesRegex(ascend.AscendError, "not owned by ASCEND"):
            ascend.make_server(self.workspace, 0)
        self.assertEqual(tree_bytes(self.workspace), before)
        for name, raw in originals.items():
            self.assertEqual((dashboard / name).read_bytes(), raw)

    def test_index_only_dashboard_is_preserved(self):
        self.initialize()
        dashboard = self.workspace / "dashboard"
        dashboard.mkdir()
        original = b"This index belongs to the user."
        (dashboard / "index.html").write_bytes(original)
        with self.assertRaisesRegex(ascend.AscendError, "not owned by ASCEND"):
            ascend.render(self.workspace, authorized=True, assets=self.assets)
        self.assertEqual((dashboard / "index.html").read_bytes(), original)
        self.assertEqual(set(p.name for p in dashboard.iterdir()), {"index.html"})

    def test_generated_dashboard_can_be_updated_using_ownership_marker(self):
        self.initialize()
        path = ascend.render(self.workspace, authorized=True, assets=self.assets)
        self.assertTrue(path.read_text(encoding="utf-8").startswith(ascend.DASHBOARD_MARKER + "\n"))
        ascend.capture(snapshot(followup=True), self.workspace, "test", authorized=True)
        ascend.render(self.workspace, authorized=True, assets=self.assets)
        self.assertIn('"captured_at":"2026-10-25T12:00:00Z"', path.read_text(encoding="utf-8"))

    def test_render_write_failure_preserves_prior_dashboard(self):
        self.initialize()
        ascend.render(self.workspace, authorized=True, assets=self.assets)
        before = tree_bytes(self.workspace)
        with mock.patch.object(ascend, "_write_new", side_effect=OSError("injected asset write failure")):
            with self.assertRaises(OSError):
                ascend.render(self.workspace, authorized=True, assets=self.assets)
        self.assertEqual(tree_bytes(self.workspace), before)

    def test_render_rename_failure_restores_prior_dashboard(self):
        self.initialize()
        ascend.render(self.workspace, authorized=True, assets=self.assets)
        before = tree_bytes(self.workspace)
        original = Path.rename

        def failing_rename(path, target):
            if path.name.startswith(".dashboard-") and not path.name.startswith(".dashboard-backup-"):
                raise OSError("injected directory switch failure")
            return original(path, target)

        with mock.patch.object(Path, "rename", failing_rename):
            with self.assertRaisesRegex(OSError, "directory switch"):
                ascend.render(self.workspace, authorized=True, assets=self.assets)
        self.assertEqual(tree_bytes(self.workspace), before)

    def test_invalid_template_does_not_write(self):
        self.initialize()
        (self.assets / "template.html").write_text("no marker", encoding="utf-8")
        before = tree_bytes(self.workspace)
        with self.assertRaisesRegex(ascend.AscendError, "exactly one"):
            ascend.render(self.workspace, authorized=True, assets=self.assets)
        self.assertEqual(tree_bytes(self.workspace), before)

    def test_server_is_loopback_only_and_does_not_expose_workspace(self):
        self.initialize()
        ascend.render(self.workspace, authorized=True, assets=self.assets)
        (self.workspace / "secret.txt").write_text("private", encoding="utf-8")
        (self.workspace / "dashboard" / "secret.txt").write_text("also private", encoding="utf-8")
        with ascend.make_server(self.workspace, 0) as server:
            self.assertEqual(server.server_address[0], "127.0.0.1")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for path, expected in (("/", 200), ("/index.html", 200), ("/styles.css", 200), ("/app.js", 200),
                                       ("/secret.txt", 404), ("/.ascend/CURRENT", 404), ("/../secret.txt", 404),
                                       ("/%2e%2e/secret.txt", 404), ("/%5c..%5csecret.txt", 404), ("/dashboard/", 404)):
                    with self.subTest(path=path):
                        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                        connection.request("GET", path)
                        response = connection.getresponse()
                        self.assertEqual(response.status, expected)
                        body = response.read()
                        self.assertNotIn(b"also private", body)
                        if expected == 200:
                            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
                            self.assertIn("connect-src 'none'", response.getheader("Content-Security-Policy"))
                        connection.close()
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request("GET", "/", headers={"Host": "attacker.example"})
                response = connection.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
                connection.close()
            finally:
                server.shutdown()
                thread.join(timeout=5)


class CliTests(unittest.TestCase):
    def test_validate_is_read_only_and_missing_acknowledgement_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "snapshot.json"
            input_path.write_bytes(ascend.canonical(snapshot()))
            before = tree_bytes(root)
            command = [sys.executable, "-B", str(SCRIPT)]
            valid = subprocess.run(command + ["validate", str(input_path)], capture_output=True, text=True, check=False)
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertIn("truth and consent are not certified", valid.stdout)
            self.assertEqual(tree_bytes(root), before)
            denied = subprocess.run(command + ["init", str(input_path), "--workspace", str(root / "workspace"),
                                               "--actor", "test"], capture_output=True, text=True, check=False)
            self.assertEqual(denied.returncode, 2)
            self.assertIn("authorization", denied.stderr)
            self.assertFalse((root / "workspace").exists())

    def test_cli_end_to_end_init_capture_verify(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            first, second = root / "first.json", root / "second.json"
            first.write_bytes(ascend.canonical(snapshot()))
            second.write_bytes(ascend.canonical(snapshot(followup=True)))
            command = [sys.executable, "-B", str(SCRIPT)]
            for args in (["init", str(first), "--workspace", str(workspace), "--actor", "Claude", "--authorize-write"],
                         ["capture", str(second), "--workspace", str(workspace), "--actor", "Codex", "--authorize-write"],
                         ["verify", "--workspace", str(workspace)]):
                result = subprocess.run(command + args, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Verified 2 capture(s)", result.stdout)


if __name__ == "__main__":
    unittest.main()
