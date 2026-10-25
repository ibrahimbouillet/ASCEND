"""Exercise the shipped demonstration through the real state/render pipeline."""
import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ascend_examples_runtime", ROOT / "skills/ascend/scripts/ascend.py")
ascend = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ascend)


class DataScript(HTMLParser):
    def __init__(self):
        super().__init__()
        self.collecting = False
        self.content = ""

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "ascend-data":
            self.collecting = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.collecting = False

    def handle_data(self, data):
        if self.collecting:
            self.content += data


class ShippedExampleTests(unittest.TestCase):
    def test_shipped_store_reaches_dashboard_with_baseline_and_unknowns_intact(self):
        baseline = ascend.read_json(ROOT / "examples/atelier-solstice/baseline.json")
        followup = ascend.read_json(ROOT / "examples/atelier-solstice/followup.json")
        with tempfile.TemporaryDirectory(prefix="ascend-example-") as directory:
            workspace = Path(directory) / "project"
            ascend.initialize(baseline, workspace, "example-test", authorized=True)
            ascend.capture(followup, workspace, "example-test", authorized=True)
            report = ascend.render(workspace, authorized=True)
            parser = DataScript()
            parser.feed(report.read_text(encoding="utf-8"))
            payload = json.loads(parser.content)
            self.assertEqual(payload["baseline"], baseline)
            self.assertEqual(payload["current"], followup)
            self.assertEqual(payload["history"], [baseline, followup])
            self.assertTrue(payload["current"]["project"]["simulation"])
            unknown_ids = {metric["id"] for metric in followup["metrics"] if metric["value"] is None}
            self.assertTrue(unknown_ids)
            for change in payload["changes"]:
                if change["metric_id"] in unknown_ids:
                    self.assertFalse(change["comparable"])
                    self.assertIsNone(change["after"])
                    self.assertIsNone(change["delta"])
            self.assertEqual(set(item.name for item in report.parent.iterdir()), ascend.ALLOWED_FILES)


if __name__ == "__main__":
    unittest.main()
