"""Behavioral tests for bounded, read-only assistant context over real storage."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_runtime import SCRIPT, ascend, snapshot, tree_bytes


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / "project"

    def store(self, baseline=None, followup=None):
        first = ascend.initialize(baseline or snapshot(), self.workspace, "Test", authorized=True)
        second = None
        if followup:
            second = ascend.capture(followup, self.workspace, "Test", authorized=True)
        return first, second

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args, "--workspace", str(self.workspace)],
                              capture_output=True, text=True, encoding="utf-8")

    def test_summary_current_baseline_measurement_and_read_only(self):
        first, second = self.store(followup=snapshot(followup=True))
        (self.workspace / ".ascend.lock").write_text("Another writer exists", encoding="utf-8")
        before = tree_bytes(self.workspace)
        result = ascend.context_summary(self.workspace)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["captures"]["baseline"]["id"], first["id"])
        self.assertEqual(result["captures"]["current"]["id"], second["id"])
        self.assertEqual(result["captures"]["current"]["captured_at"], "2026-10-25T12:00:00Z")
        self.assertEqual(result["captures"]["count"], 2)
        self.assertEqual(result["project"]["objective"], "Complete a working page.")
        self.assertEqual(result["project"]["domain"], "education")
        self.assertTrue(result["project"]["simulation"])
        metric = result["metrics"]["items"][0]
        self.assertEqual((metric["value"], metric["unit"], metric["period_start"]), (3, "lessons", "2026-10-19"))
        self.assertEqual(metric["baseline_comparison"]["before"], 0)
        self.assertEqual(metric["baseline_comparison"]["delta"], 3)
        self.assertTrue(metric["baseline_comparison"]["comparable"])
        self.assertEqual(result["sources"]["counts_by_status"], {"available": 1})
        self.assertEqual(result["coverage"]["counts_by_status"], {"examined": 1})
        self.assertNotIn("history", result)
        self.assertNotIn("detail", result["findings"]["items"][0])
        self.assertEqual(before, tree_bytes(self.workspace))

    def test_unknown_values_and_explicit_coverage_gaps(self):
        followup = snapshot(followup=True)
        followup["metrics"][0]["value"] = None
        followup["coverage"].append({"area": "Learner outcome", "status": "unavailable",
                                     "source_ids": [], "note": "No learner outcome assessment supplied."})
        self.store(followup=followup)
        result = ascend.context_summary(self.workspace)
        comparison = result["metrics"]["items"][0]["baseline_comparison"]
        self.assertIsNone(result["metrics"]["items"][0]["value"])
        self.assertFalse(comparison["comparable"])
        self.assertIsNone(comparison["delta"])
        self.assertIn("unavailable", comparison["reason"])
        self.assertEqual(result["coverage"]["gaps"]["items"][0]["note"], "No learner outcome assessment supplied.")

    def test_new_removed_and_incompatible_metrics_remain_explicit(self):
        baseline, followup = snapshot(), snapshot(followup=True)
        removed = copy.deepcopy(baseline["metrics"][0])
        removed["id"] = "metric-removed"
        baseline["metrics"].append(removed)
        new = copy.deepcopy(followup["metrics"][0])
        new["id"] = "metric-new"
        followup["metrics"].append(new)
        followup["metrics"][0]["comparability_key"] = "changed-definition"
        self.store(baseline, followup)
        result = ascend.context_summary(self.workspace)
        changes = {x["id"]: x["baseline_comparison"] for x in result["metrics"]["items"]}
        self.assertIn("definition", changes["metric-lessons"]["reason"])
        self.assertIn("missing", changes["metric-new"]["reason"])
        removed_result = result["removed_metric_comparisons"]["items"][0]
        self.assertEqual(removed_result["metric_id"], "metric-removed")
        self.assertFalse(removed_result["comparable"])

    def test_priority_is_separate_from_confidence_and_consent_is_declared(self):
        data = snapshot()
        data["findings"][0].update(severity="yellow", confidence="high")
        urgent = copy.deepcopy(data["findings"][0])
        urgent.update(id="finding-urgent", kind="hypothesis", severity="red", confidence="low")
        data["findings"].append(urgent)
        action = copy.deepcopy(data["actions"][0])
        action.update(id="action-urgent", finding_ids=["finding-urgent"], status="authorized", authorization="Human request 42")
        data["actions"].append(action)
        completed = copy.deepcopy(action)
        completed.update(id="action-done", status="completed")
        data["actions"].append(completed)
        self.store(data)
        result = ascend.context_summary(self.workspace)
        first = result["findings"]["items"][0]
        self.assertEqual((first["id"], first["kind"], first["confidence"]), ("finding-urgent", "hypothesis", "low"))
        self.assertEqual(first["source_ids"]["items"], ["source-notes"])
        first_action = result["pending_actions"]["items"][0]
        self.assertEqual((first_action["id"], first_action["status"]), ("action-urgent", "authorized"))
        self.assertTrue(first_action["authorization"]["reference_present"])
        self.assertFalse(first_action["authorization"]["consent_verified_by_runtime"])
        self.assertEqual(result["pending_actions"]["total"], 2)

    def test_inspect_explicit_edges_and_reference_edges_without_graph(self):
        data = snapshot()
        data["links"] = []
        self.store(data)
        before = tree_bytes(self.workspace)
        source = ascend.inspect_record(self.workspace, "source-notes")
        self.assertEqual(source["type"], "source")
        self.assertEqual(source["content"], data["sources"][0])
        self.assertEqual({x["type"] for x in source["neighbors"]}, {"metric", "finding", "benchmark", "coverage"})
        self.assertTrue(all(x["relation"] == "source_ids" for x in source["neighbors"]))
        finding = ascend.inspect_record(self.workspace, "finding-practice")
        self.assertEqual({x["relation"] for x in finding["neighbors"]}, {"source_ids", "metric_ids", "finding_ids"})
        self.assertNotIn("history", finding)
        self.assertEqual(ascend.inspect_record(self.workspace, "test-project")["neighbors"], [])
        self.assertEqual(before, tree_bytes(self.workspace))

    def test_inspect_explicit_graph_direction(self):
        self.store()
        result = ascend.inspect_record(self.workspace, "action-practice")
        relation = next(x for x in result["neighbors"] if x["relation"] == "motivates")
        self.assertEqual((relation["from"], relation["to"]), ("finding-practice", "action-practice"))
        self.assertEqual(relation["id"], "finding-practice")

    def test_summary_truncation_is_bounded_and_explicit(self):
        data = snapshot()
        for i in range(12):
            for group in ("sources", "metrics", "findings", "actions"):
                item = copy.deepcopy(data[group][0])
                item["id"] = f"{group}-{i}"
                data[group].append(item)
            data["coverage"].append({"area": f"Gap {i}", "status": "partial", "source_ids": [], "note": "z" * 2000})
        data["project"]["constraints"] = ["x" * 2000] * 13
        data["project"]["objective"] = "y" * 2000
        data["metrics"][0]["label"] = "m" * 2000
        data["findings"][0]["source_ids"] = [x["id"] for x in data["sources"]]
        data["findings"][0]["metric_ids"] = [x["id"] for x in data["metrics"]]
        data["actions"][0]["finding_ids"] = [x["id"] for x in data["findings"]]
        self.store(data)
        result = ascend.context_summary(self.workspace)
        for key in ("sources", "metrics", "findings", "pending_actions"):
            self.assertEqual((len(result[key]["items"]), result[key]["total"], result[key]["omitted"]), (10, 13, 3))
        self.assertEqual(result["coverage"]["gaps"]["omitted"], 2)
        self.assertEqual(result["project"]["constraints"]["omitted"], 3)
        finding = next(x for x in result["findings"]["items"] if x["id"] == "finding-practice")
        self.assertEqual(finding["source_ids"]["omitted"], 3)
        self.assertEqual(finding["metric_ids"]["omitted"], 3)
        self.assertEqual(len(ascend.inspect_record(self.workspace, "finding-practice")["content"]["source_ids"]), 13)
        text = json.dumps(result)
        self.assertIn("truncated", text)
        self.assertNotIn("y" * 601, text)
        self.assertNotIn("x" * 601, text)
        self.assertNotIn("m" * 601, text)
        self.assertNotIn("z" * 601, text)
        self.assertIn("inspect --workspace", result["pointers"]["inspect"])

    def test_cli_json_markdown_unknown_id_and_no_file_creation(self):
        self.store()
        before = tree_bytes(self.workspace)
        result = self.cli("summary")
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed, ascend.context_summary(self.workspace))
        markdown = self.cli("summary", "--format", "markdown")
        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertEqual(markdown.stdout.rstrip("\n"), ascend.context_markdown(parsed))
        self.assertNotIn("```", markdown.stdout)
        inspected = self.cli("inspect", "--id", "metric-lessons")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["id"], "metric-lessons")
        unknown = self.cli("inspect", "--id", "other-project-record")
        self.assertEqual(unknown.returncode, 2)
        self.assertEqual(unknown.stdout, "")
        self.assertIn("unknown current record ID", unknown.stderr)
        self.assertEqual(before, tree_bytes(self.workspace))

    @staticmethod
    def table_rows(markdown, section):
        block = markdown.split("## " + section, 1)[1].split("\n## ", 1)[0]
        rows = [line[2:-2].split(" | ") for line in block.splitlines() if line.startswith("| ")]
        return [dict(zip(rows[0], row)) for row in rows[2:]]

    def test_markdown_keeps_metric_values_periods_and_comparison_semantics(self):
        self.store(followup=snapshot(followup=True))
        summary = ascend.context_summary(self.workspace)
        before = copy.deepcopy(summary)
        markdown = ascend.context_markdown(summary)
        rows = self.table_rows(markdown, "Metrics")
        for row, metric in zip(rows, summary["metrics"]["items"]):
            old, change = metric["baseline_measurement"], metric["baseline_comparison"]
            self.assertEqual(row["ID"], metric["id"])
            self.assertEqual(row["Current"], f"{metric['value']} {metric['unit']}")
            self.assertEqual(row["Period"], f"{metric['period_start']} to {metric['period_end']}")
            self.assertEqual(row["Baseline"], f"{old['value']} {old['unit']}; {old['period_start']} to {old['period_end']}; definition: {old['comparability_key']}")
            self.assertEqual(row["Change"], f"delta {change['delta']}; comparable: true; {change['reason']}")
            self.assertEqual(row["Sources"].split(", "), metric["source_ids"]["items"])
        self.assertEqual(len(rows), summary["metrics"]["total"])
        self.assertIn(summary["captures"]["baseline"]["id"], markdown)
        self.assertIn(summary["captures"]["current"]["id"], markdown)
        self.assertEqual(summary, before)
        self.assertLess(len(markdown), len(json.dumps(summary, indent=2)))

    def test_markdown_unknowns_priority_and_authorization_are_not_reinterpreted(self):
        data = snapshot(followup=True)
        data["metrics"][0]["value"] = None
        urgent = copy.deepcopy(data["findings"][0])
        urgent.update(id="finding-urgent", kind="hypothesis", severity="red", confidence="low")
        data["findings"].append(urgent)
        data["actions"][0].update(status="authorized", authorization="Human request 42", finding_ids=["finding-urgent"])
        self.store(snapshot(), data)
        summary = ascend.context_summary(self.workspace)
        markdown = ascend.context_markdown(summary)
        metric = self.table_rows(markdown, "Metrics")[0]
        self.assertEqual(metric["Current"], "unknown lessons")
        self.assertEqual(metric["Change"], "delta unknown; comparable: false; " + summary["metrics"]["items"][0]["baseline_comparison"]["reason"])
        findings = self.table_rows(markdown, "Findings")
        self.assertEqual([x["ID"] for x in findings], [x["id"] for x in summary["findings"]["items"]])
        self.assertEqual((findings[0]["Kind"], findings[0]["Priority"], findings[0]["Confidence"]), ("hypothesis", "red", "low"))
        action = self.table_rows(markdown, "Pending actions")[0]
        self.assertEqual((action["Status"], action["Authorization"]), ("authorized", "declared: Human request 42"))
        self.assertIn("does not prove human consent", markdown)
        self.assertIn("Changes do not establish causality", markdown)

    def test_markdown_preserves_omissions_and_escapes_untrusted_cells(self):
        data = snapshot()
        for index in range(12):
            item = copy.deepcopy(data["metrics"][0])
            item["id"] = f"metric-extra-{index}"
            data["metrics"].append(item)
        data["coverage"] = [{"area": "Unknown outcome", "status": "unavailable", "source_ids": [], "note": "Not assessed."}]
        data["metrics"][0]["label"] = "A | table\n# heading ``` <script>"
        data["findings"][0]["title"] = "x" * 2000
        self.store(data)
        summary = ascend.context_summary(self.workspace)
        markdown = ascend.context_markdown(summary)
        rows = self.table_rows(markdown, "Metrics")
        self.assertEqual(len(rows), 10)
        self.assertEqual({row["ID"] for row in rows}, {x["id"] for x in summary["metrics"]["items"]})
        self.assertIn("## Metrics (10/13 shown; 3 omitted)", markdown)
        self.assertIn("A \\| table<br>\\# heading \\`\\`\\` &lt;script&gt;", markdown)
        self.assertNotIn("<script>", markdown)
        self.assertNotIn("\n# heading", markdown)
        self.assertNotIn("```", markdown)
        self.assertIn("[truncated; inspect this record for full text]", markdown.replace("\\[", "[").replace("\\]", "]"))
        self.assertIn("Unknown outcome: unavailable; sources: none recorded; Not assessed.", markdown)
        self.assertIn(summary["pointers"]["full_current"], markdown)
        self.assertIn(summary["pointers"]["inspect"], markdown)

    def test_corrupt_ancestry_fails_closed_without_writes(self):
        first, _ = self.store(followup=snapshot(followup=True))
        baseline = self.workspace / ".ascend" / "generations" / first["generation"] / "snapshot.json"
        baseline.write_bytes(baseline.read_bytes() + b" ")
        before = tree_bytes(self.workspace)
        for args in (("summary",), ("inspect", "--id", "metric-lessons")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("SHA256 mismatch", result.stderr)
        self.assertEqual(before, tree_bytes(self.workspace))

    def test_missing_workspace_is_not_created(self):
        for args in (("summary",), ("inspect", "--id", "test-project")):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(self.workspace.exists())


if __name__ == "__main__":
    unittest.main()
