/* Optional browser QA. Requires Playwright and an installed Chromium binary. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

async function main() {
  const url = process.argv[2] || "http://127.0.0.1:8765";
  const baselineUrl = process.argv[3] || "http://127.0.0.1:8766";
  const out = path.resolve(process.argv[4] || ".local/browser-qa");
  fs.mkdirSync(out, { recursive: true });
  const fixture = JSON.parse(
    fs.readFileSync(
      path.join(__dirname, "../examples/atelier-solstice/followup.json"),
      "utf8",
    ),
  );
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {}),
  });
  const checks = [];
  const pass = (name) => checks.push({ name, passed: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      deviceScaleFactor: 1,
    });
    const errors = [],
      external = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("request", (request) => {
      if (
        !request.url().startsWith(url) &&
        !request.url().startsWith(baselineUrl)
      )
        external.push(request.url());
    });
    await page.goto(url, { waitUntil: "networkidle" });
    assert.equal(await page.title(), `ASCEND · ${fixture.project.name}`);
    assert.equal(
      await page
        .getByRole("heading", { name: fixture.project.name, exact: true })
        .count(),
      1,
    );
    assert.equal(
      await page.getByRole("region", { name: "Simulation notice" }).isVisible(),
      true,
    );
    pass("Project identity and explicit simulation label");
    assert.equal(
      await page.locator(".metric-card").count(),
      fixture.metrics.length,
    );
    const orders = fixture.metrics.find((m) => /orders/i.test(m.label));
    const unknown = fixture.metrics.find((m) => m.value === null);
    assert.ok(orders && unknown);
    const unknownCard = page
      .locator(".metric-card")
      .filter({
        has: page.getByRole("heading", { name: unknown.label, exact: true }),
      });
    assert.ok((await unknownCard.textContent()).includes("Not measured"));
    assert.ok(
      (await unknownCard.locator(".metric-value").textContent()).includes("—"),
    );
    pass("Unknown metric remains unavailable rather than zero");
    assert.equal(
      await page.locator(".finding").count(),
      fixture.findings.length,
    );
    const filter = page.getByRole("button", { name: "Unknown", exact: true });
    await filter.click();
    assert.equal(await filter.getAttribute("aria-pressed"), "true");
    assert.equal(
      await page.locator(".finding").count(),
      fixture.findings.filter((f) => f.severity === "grey").length,
    );
    await page
      .getByRole("button", { name: "All findings", exact: true })
      .click();
    assert.equal(
      await page.locator(".finding").count(),
      fixture.findings.length,
    );
    const finding = page.locator(".finding").first();
    await finding.locator("summary").click();
    assert.equal(await finding.locator(".evidence-list").isVisible(), true);
    pass("Audit filtering and expandable source evidence");
    await page
      .getByRole("link", { name: "Knowledge map", exact: true })
      .click();
    const graphNode = page.getByRole("button", { name: /^Source:/ }).first();
    await graphNode.focus();
    await page.keyboard.press("Enter");
    assert.equal(await graphNode.getAttribute("aria-pressed"), "true");
    assert.ok(
      (await page.locator("#node-detail").textContent()).includes(
        "relationship",
      ),
    );
    const related = page.locator("#node-detail button").first();
    if (await related.count()) {
      await related.click();
      assert.equal(
        await page.locator('.graph-node[aria-pressed="true"]').count(),
        1,
      );
    }
    pass("Keyboard graph selection and linked-record inspection");
    const action = page.locator(".action-card").first();
    await action.locator("summary").click();
    assert.ok((await action.textContent()).includes("Authorization record"));
    assert.equal(
      await page
        .getByRole("button", { name: /^(approve|execute|publish)$/i })
        .count(),
      0,
    );
    pass("Action inspection never offers execution or approval");
    const selector = page.getByRole("combobox", {
      name: "Choose metric for evolution chart",
    });
    await selector.selectOption(orders.id);
    assert.equal(await page.locator("#evolution-chart svg").count(), 1);
    assert.ok(
      (
        await page.locator("#evolution-chart svg").getAttribute("aria-label")
      ).includes("0"),
    );
    await selector.selectOption(unknown.id);
    assert.equal(
      await page
        .getByText("These measurements are not comparable.", { exact: true })
        .isVisible(),
      true,
    );
    pass("Zero orders and unavailable evolution handled distinctly");
    await selector.selectOption(fixture.metrics[0].id);
    await page.getByRole("link", { name: "Overview", exact: true }).click();
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await page.waitForFunction(() => window.scrollY === 0);
    await page.screenshot({ path: path.join(out, "desktop.png") });
    await page.screenshot({
      path: path.join(out, "desktop-full.png"),
      fullPage: true,
    });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    );
    pass("Desktop layout fits viewport");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(url, { waitUntil: "networkidle" });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    );
    assert.equal(
      await page
        .getByRole("heading", { name: fixture.project.name, exact: true })
        .isVisible(),
      true,
    );
    await page.screenshot({ path: path.join(out, "mobile.png") });
    await page.screenshot({
      path: path.join(out, "mobile-full.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "Unknown", exact: true }).click();
    assert.equal(
      await page.locator(".finding").count(),
      fixture.findings.filter((f) => f.severity === "grey").length,
    );
    pass("390px layout and audit interaction");
    await page.goto(baselineUrl, { waitUntil: "networkidle" });
    assert.equal(
      await page
        .getByText("A baseline, not a trend.", { exact: true })
        .isVisible(),
      true,
    );
    assert.equal(await page.locator("#evolution-chart svg").count(), 0);
    pass("Single capture has no fabricated trend");
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    pass("No browser errors or external network requests");
    fs.writeFileSync(
      path.join(out, "results.json"),
      JSON.stringify(
        {
          checks,
          passed: checks.length,
          browser_errors: errors,
          external_requests: external,
        },
        null,
        2,
      ) + "\n",
    );
    console.log(
      JSON.stringify({ passed: checks.length, screenshot_directory: out }),
    );
  } finally {
    await browser.close();
  }
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
