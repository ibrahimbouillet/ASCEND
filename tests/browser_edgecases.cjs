"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const { chromium } = require("playwright");

const repo = path.resolve(__dirname, "..");
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "ascend-browser-"));
const python = process.env.ASCEND_PYTHON || "python";
const processes = [];
const checks = [];
const preparation = String.raw`
import copy, json, sys
from pathlib import Path
root, target = map(Path, sys.argv[1:])
sys.path.insert(0, str(root / 'skills/ascend/scripts'))
import ascend
base = json.loads((root/'examples/atelier-solstice/baseline.json').read_text(encoding='utf-8'))
later = json.loads((root/'examples/atelier-solstice/followup.json').read_text(encoding='utf-8'))
hostile = copy.deepcopy(base)
hostile['project']['name'] = '</script><script>globalThis.ascendInjected=true</script>' + 'X' * 140
hostile['sources'][0]['title'] = '<img src=x onerror="globalThis.ascendInjected=true">'
hostile['sources'][0]['locator'] = 'javascript:globalThis.ascendInjected=true'
ascend.initialize(hostile, target/'hostile', 'browser-qa', authorized=True)
ascend.render(target/'hostile', authorized=True)
ascend.initialize(base, target/'intermediate', 'browser-qa', authorized=True)
middle = copy.deepcopy(base)
middle['captured_at'] = '2026-10-21T10:00:00Z'
middle['metrics'][0].update(value=999,period_start='2026-10-18',period_end='2026-10-20')
ascend.capture(middle, target/'intermediate', 'browser-qa', authorized=True)
ascend.capture(later, target/'intermediate', 'browser-qa', authorized=True)
ascend.render(target/'intermediate', authorized=True)
ascend.initialize(base, target/'unequal', 'browser-qa', authorized=True)
unequal = copy.deepcopy(later)
unequal['metrics'][0]['period_end'] = '2026-10-23'
ascend.capture(unequal, target/'unequal', 'browser-qa', authorized=True)
ascend.render(target/'unequal', authorized=True)
`;
function server(name) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      python,
      [
        path.join(repo, "skills/ascend/scripts/ascend.py"),
        "serve",
        "--workspace",
        path.join(tempRoot, name),
        "--port",
        "0",
      ],
      { windowsHide: true, stdio: ["ignore", "pipe", "pipe"] },
    );
    processes.push(child);
    let output = "";
    const deadline = setTimeout(
      () => reject(new Error("Local test server did not start")),
      20000,
    );
    child.stdout.on("data", (data) => {
      output += data;
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+\//);
      if (match) {
        clearTimeout(deadline);
        resolve(match[0]);
      }
    });
    child.once("error", (error) => {
      clearTimeout(deadline);
      reject(error);
    });
    child.once("exit", (code) => {
      clearTimeout(deadline);
      if (!output.includes("http://"))
        reject(new Error(`Local test server exited: ${code}`));
    });
  });
}
async function main() {
  let browser;
  try {
    const prepared = spawnSync(
      python,
      ["-B", "-c", preparation, repo, tempRoot],
      { windowsHide: true, encoding: "utf8" },
    );
    assert.equal(prepared.status, 0, prepared.stderr);
    const urls = await Promise.all(
      ["hostile", "intermediate", "unequal"].map(server),
    );
    browser = await chromium.launch({
      headless: true,
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
        ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
        : {}),
    });
    const page = await browser.newPage({
      viewport: { width: 390, height: 844 },
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(urls[0], { waitUntil: "networkidle" });
    assert.equal(
      await page.evaluate(() => globalThis.ascendInjected),
      undefined,
    );
    assert.ok(
      (await page.locator("#project-name").textContent()).includes("</script>"),
    );
    assert.equal(await page.locator('a[href^="javascript:"]').count(), 0);
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    );
    checks.push(
      "Hostile strings render as text, unsafe source URLs stay inert, long names fit 390px",
    );
    await page.goto(urls[1], { waitUntil: "networkidle" });
    const line = page.locator("#evolution-chart polyline");
    assert.equal(await line.count(), 0);
    const actualPoints = page.locator("#evolution-chart circle");
    assert.equal(await actualPoints.count(), 2);
    assert.deepEqual(
      await actualPoints.evaluateAll((points) =>
        points.map((point) => Number(point.getAttribute("cx"))),
      ),
      [48, 478],
    );
    assert.equal(
      await page.locator("#evolution-chart .chart-gap-note").isVisible(),
      true,
    );
    assert.ok(
      (
        await page.locator("#evolution-chart .chart-gap-note").textContent()
      ).includes("Gap at 21 Oct 2026"),
    );
    assert.ok(
      !(
        await page.locator("#evolution-chart svg").getAttribute("aria-label")
      ).includes("999"),
    );
    assert.ok(
      (
        await page.locator("#evolution-chart svg").getAttribute("aria-label")
      ).includes("gap: unavailable or incompatible measurement"),
    );
    assert.equal(await page.locator("#history-list li").count(), 3);
    checks.push(
      "Incompatible intermediate capture retains its x-position and gap explanation; isolated numeric points have no cross-gap line",
    );
    await page.goto(urls[2], { waitUntil: "networkidle" });
    assert.equal(await page.locator("#evolution-chart svg").count(), 0);
    assert.equal(
      await page
        .getByText("These measurements are not comparable.", { exact: true })
        .isVisible(),
      true,
    );
    const firstMetric = page.locator(".metric-card").first();
    assert.equal(await firstMetric.locator(".metric-delta").count(), 0);
    checks.push("Unequal periods produce no trend or numeric change badge");
    assert.deepEqual(errors, []);
    const output = path.join(repo, ".local/browser-qa/edge-results.json");
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(
      output,
      JSON.stringify(
        { passed: checks.length, checks, browser_errors: errors },
        null,
        2,
      ) + "\n",
    );
    console.log(JSON.stringify({ passed: checks.length, checks }));
  } finally {
    if (browser) await browser.close();
    await Promise.all(
      processes.map(
        (child) =>
          new Promise((resolve) => {
            if (child.exitCode !== null) return resolve();
            child.once("exit", resolve);
            child.kill();
          }),
      ),
    );
    // Delete only the exact temporary directory this test created.
    assert.equal(path.dirname(tempRoot), path.resolve(os.tmpdir()));
    assert.ok(path.basename(tempRoot).startsWith("ascend-browser-"));
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
