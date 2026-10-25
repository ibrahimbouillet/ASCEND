(() => {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const el = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = String(value);
    return node;
  };
  const svgEl = (tag, attrs = {}, value) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs).forEach(([key, item]) =>
      node.setAttribute(key, String(item)),
    );
    if (value !== undefined) node.textContent = String(value);
    return node;
  };
  const list = (value) => (Array.isArray(value) ? value : []);
  const text = (id, value) => {
    const node = byId(id);
    if (node) node.textContent = value == null ? "Not recorded" : String(value);
  };
  const date = (value) => {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
      ? "Date not recorded"
      : parsed.toLocaleDateString("en-GB", {
          day: "numeric",
          month: "short",
          year: "numeric",
          timeZone: "UTC",
        });
  };
  const number = (value) =>
    typeof value === "number" && Number.isFinite(value)
      ? new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 }).format(
          value,
        )
      : "—";
  const label = (value) =>
    String(value || "unknown")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  const priorityLabels = {
    red: "Urgent",
    yellow: "Improve",
    green: "Working",
    grey: "Unknown",
  };
  const kindLabels = {
    observed: "Observed fact",
    hypothesis: "Hypothesis",
    unknown: "Information gap",
  };
  let payload;
  try {
    payload = JSON.parse(byId("ascend-data").textContent);
    if (!payload.current || !payload.current.project)
      throw new Error("A current project snapshot is required.");
  } catch (error) {
    const panel = el("div", "report-error");
    panel.append(
      el("h1", "", "This report could not be loaded."),
      el(
        "p",
        "",
        "The embedded snapshot is missing or invalid. Regenerate the local dashboard using ASCEND.",
      ),
      el("p", "", error.message),
    );
    byId("main").replaceChildren(panel);
    return;
  }
  const current = payload.current;
  const project = current.project;
  const sources = new Map(list(current.sources).map((item) => [item.id, item]));
  const metrics = list(current.metrics);
  const findings = list(current.findings);
  const actions = list(current.actions);
  const changes = list(payload.changes);
  const sourceTitle = (id) =>
    sources.get(id)?.title || `Unresolved source: ${id}`;
  const valueWithUnit = (metric) => {
    const value = number(metric?.value);
    if (value === "—") return value;
    const unit = metric?.unit || "";
    return /^(EUR|USD|GBP)$/i.test(unit)
      ? new Intl.NumberFormat("en-GB", {
          style: "currency",
          currency: unit.toUpperCase(),
          maximumFractionDigits: 2,
        }).format(metric.value)
      : `${value}${unit === "%" ? "%" : unit ? ` ${unit}` : ""}`;
  };
  const safeLink = (value) => {
    try {
      const url = new URL(value);
      return ["https:", "http:"].includes(url.protocol) ? url.href : null;
    } catch {
      return null;
    }
  };
  function renderEvidence(ids, target) {
    const evidence = el("ul", "evidence-list");
    list(ids).forEach((id) => {
      const source = sources.get(id);
      const item = el("li", "evidence-item");
      item.append(el("strong", "", sourceTitle(id)));
      if (source) {
        item.append(
          el(
            "span",
            "",
            `${label(source.kind)} · ${label(source.status)} · ${date(source.captured_at)}`,
          ),
        );
        const link = safeLink(source.locator);
        if (link) {
          const anchor = el("a", "", source.locator);
          anchor.href = link;
          anchor.target = "_blank";
          anchor.rel = "noopener noreferrer";
          item.append(anchor);
        } else if (source.locator) item.append(el("span", "", source.locator));
        if (source.note) item.append(el("span", "", source.note));
      }
      evidence.append(item);
    });
    if (!evidence.children.length)
      evidence.append(
        el("li", "detail-text", "No supporting source was recorded."),
      );
    target.append(evidence);
  }
  const initials = String(project.name || "Project")
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0] || "")
    .join("")
    .toUpperCase();
  text("sidebar-project", project.name);
  text("project-initials", initials);
  text("project-name", project.name);
  text("project-domain", project.domain);
  text("project-summary", project.summary);
  text("project-objective", project.objective);
  text("capture-date", date(current.captured_at));
  text(
    "baseline-label",
    payload.baseline?.captured_at === current.captured_at
      ? "Baseline recorded"
      : "Current snapshot",
  );
  text("generated-at", date(payload.generated_at));
  text("audit-count", findings.length);
  document.title = `ASCEND · ${project.name || "Project intelligence"}`;
  if (/^#[\da-f]{6}$/i.test(project.brand?.accent || ""))
    document.documentElement.style.setProperty(
      "--accent",
      project.brand.accent,
    );
  byId("simulation-notice").hidden = project.simulation !== true;
  metrics.forEach((metric, index) => {
    const card = el("article", "metric-card");
    const top = el("div", "metric-top");
    top.append(
      el("h3", "metric-label", metric.label),
      el("span", "metric-index", String(index + 1).padStart(2, "0")),
    );
    const value = el("div", "metric-value", valueWithUnit(metric));
    const caption = el("p", "metric-caption");
    const change = changes.find((item) => item.metric_id === metric.id);
    if (change?.comparable && Number.isFinite(change.delta))
      caption.append(
        el(
          "span",
          "metric-delta",
          `${change.delta > 0 ? "+" : ""}${number(change.delta)} since baseline`,
        ),
      );
    caption.append(
      document.createTextNode(
        metric.value == null
          ? "Not measured · no value assumed"
          : metric.period_start && metric.period_end
            ? `${date(metric.period_start)} – ${date(metric.period_end)}`
            : "Measurement period not recorded",
      ),
    );
    card.append(top, value, caption);
    byId("metrics").append(card);
  });
  if (!metrics.length)
    byId("metrics").append(
      el("p", "empty-state", "No metrics have been recorded."),
    );
  const coverage = list(current.coverage);
  text(
    "coverage-summary",
    `${coverage.filter((item) => item.status === "examined").length} / ${coverage.length} examined`,
  );
  coverage.forEach((item) => {
    const row = el("div", "coverage-row");
    const detail = el("div");
    detail.append(el("span", "coverage-area", item.area));
    if (item.note) detail.append(el("p", "coverage-note", item.note));
    row.append(
      detail,
      el("span", `coverage-status ${item.status}`, label(item.status)),
    );
    byId("coverage-list").append(row);
  });
  if (!coverage.length)
    byId("coverage-list").append(
      el("p", "detail-text", "Analysis coverage has not been recorded."),
    );
  list(project.constraints).forEach((item) =>
    byId("constraints").append(el("li", "", item)),
  );
  if (!list(project.constraints).length)
    byId("constraints").append(
      el(
        "li",
        "",
        "No constraints recorded. Confirm resources and limits before choosing actions.",
      ),
    );
  function renderFindings(filter = "all") {
    const target = byId("findings");
    target.replaceChildren();
    const visible = findings.filter(
      (item) => filter === "all" || item.severity === filter,
    );
    text(
      "findings-count",
      `${visible.length} ${visible.length === 1 ? "finding" : "findings"}`,
    );
    visible.forEach((finding) => {
      const severity = Object.hasOwn(priorityLabels, finding.severity)
        ? finding.severity
        : "grey";
      const card = el("details", `finding ${severity}`);
      const summary = el("summary");
      const main = el("div", "finding-summary");
      main.append(el("h3", "", finding.title));
      const meta = el("div", "finding-meta");
      meta.append(
        el("span", "", kindLabels[finding.kind] || "Unclassified"),
        el("span", "", `${label(finding.confidence)} confidence`),
        el(
          "span",
          "",
          `${list(finding.source_ids).length} source${list(finding.source_ids).length === 1 ? "" : "s"}`,
        ),
      );
      main.append(meta);
      summary.append(
        el(
          "span",
          "priority-mark",
          { red: "!", yellow: "↗", green: "✓", grey: "?" }[severity],
        ),
        main,
        el("span", "finding-priority", priorityLabels[severity]),
        el("span", "expand-icon", "+"),
      );
      const detail = el("div", "finding-detail");
      detail.append(
        el("p", "", finding.detail),
        el("span", "detail-label", "Verification needed"),
        el(
          "p",
          "detail-text",
          finding.verification || "No verification step recorded.",
        ),
        el("span", "detail-label", "Supporting evidence"),
      );
      renderEvidence(finding.source_ids, detail);
      if (list(finding.metric_ids).length) {
        detail.append(
          el("span", "detail-label", "Connected measurements"),
          el(
            "p",
            "detail-text",
            finding.metric_ids
              .map((id) => {
                const metric = metrics.find((item) => item.id === id);
                return metric
                  ? `${metric.label}: ${valueWithUnit(metric)}`
                  : `Unresolved metric: ${id}`;
              })
              .join(" · "),
          ),
        );
      }
      card.append(summary, detail);
      target.append(card);
    });
    if (!visible.length)
      target.append(el("p", "empty-state", "No findings in this category."));
  }
  document.querySelectorAll("[data-filter]").forEach((button) =>
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-filter]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      renderFindings(button.dataset.filter);
    }),
  );
  renderFindings();
  actions.forEach((action, index) => {
    const card = el("article", "action-card");
    const top = el("div", "action-top");
    const status = [
      "proposed",
      "authorized",
      "in_progress",
      "completed",
      "blocked",
      "cancelled",
    ].includes(action.status)
      ? action.status
      : "proposed";
    top.append(
      el(
        "span",
        "action-index",
        `ACTION ${String(index + 1).padStart(2, "0")}`,
      ),
      el("span", `action-status ${status}`, label(status)),
    );
    const facts = el("div", "action-facts");
    [
      ["Estimated cost", action.cost],
      ["Expected outcome", action.expected_outcome],
    ].forEach(([key, value]) => {
      const box = el("div");
      box.append(
        el("span", "detail-label", key),
        el("p", "", value || "Not recorded"),
      );
      facts.append(box);
    });
    const details = el("details");
    details.append(el("summary", "", "Inspect plan & authorization"));
    const inspection = el("div", "action-inspection");
    inspection.append(
      el("span", "detail-label", "How to verify"),
      el("p", "", action.verification || "No verification method recorded."),
      el("span", "detail-label", "Authorization record"),
      el(
        "p",
        "",
        action.authorization ||
          "No authorization recorded. This report cannot authorize or execute an action.",
      ),
      el("span", "detail-label", "Connected findings"),
      el(
        "p",
        "",
        list(action.finding_ids)
          .map(
            (id) =>
              findings.find((item) => item.id === id)?.title ||
              `Unresolved finding: ${id}`,
          )
          .join(" · ") || "None recorded.",
      ),
    );
    details.append(inspection);
    card.append(
      top,
      el("h3", "", action.title),
      el("p", "", action.rationale),
      facts,
      details,
    );
    byId("actions-list").append(card);
  });
  if (!actions.length)
    byId("actions-list").append(
      el(
        "p",
        "empty-state",
        "No actions proposed. Establish the evidence before choosing a plan.",
      ),
    );
  list(current.benchmarks).forEach((benchmark) => {
    const card = el("article", "benchmark-card");
    card.append(
      el(
        "div",
        "benchmark-kicker",
        benchmark.simulated
          ? "◈  SIMULATED COMPARISON"
          : "↗  RECORDED COMPARISON",
      ),
      el("h3", "", benchmark.label),
      el("p", "", benchmark.comparison),
    );
    const limits = el("div", "limitation-box");
    limits.append(
      el("span", "detail-label", "Where this comparison stops"),
      el(
        "p",
        "",
        benchmark.limitations ||
          "Limitations have not been recorded. Do not treat this comparison as a validated recommendation.",
      ),
    );
    const details = el("details");
    details.append(el("summary", "", "Inspect reference sources"));
    renderEvidence(benchmark.source_ids, details);
    card.append(limits, details);
    byId("benchmarks-list").append(card);
  });
  if (!list(current.benchmarks).length)
    byId("benchmarks-list").append(
      el(
        "p",
        "empty-state",
        "No comparisons recorded. Relevant references still need to be researched.",
      ),
    );
  const nodes = [
    ...list(current.sources).map((item) => ({
      ...item,
      type: "source",
      label: item.title,
    })),
    ...metrics.map((item) => ({ ...item, type: "metric", label: item.label })),
    ...findings.map((item) => ({
      ...item,
      type: "finding",
      label: item.title,
    })),
    ...actions.map((item) => ({ ...item, type: "action", label: item.title })),
  ];
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const graphLinks = list(current.links).filter(
    (link) => nodeMap.has(link.from) && nodeMap.has(link.to),
  );
  const nodeElements = new Map();
  const lineElements = [];
  function selectNode(id) {
    const node = nodeMap.get(id);
    if (!node) return;
    nodeElements.forEach((item, key) => {
      item.classList.toggle("selected", key === id);
      item.setAttribute("aria-pressed", String(key === id));
    });
    lineElements.forEach(({ element, link }) =>
      element.classList.toggle("selected", link.from === id || link.to === id),
    );
    const detail = byId("node-detail");
    detail.replaceChildren(
      el("span", "section-eyebrow", `${node.type.toUpperCase()} / ${node.id}`),
      el("h3", "", node.label),
    );
    const description =
      node.detail ||
      node.rationale ||
      node.note ||
      (node.type === "metric"
        ? `${valueWithUnit(node)} · ${date(node.period_start)} – ${date(node.period_end)}`
        : node.locator || "No description recorded.");
    detail.append(el("p", "", description));
    if (node.type === "finding")
      detail.append(
        el(
          "p",
          "",
          `${kindLabels[node.kind] || "Unclassified"} · ${label(node.confidence)} confidence · ${priorityLabels[node.severity] || "Unknown"} priority`,
        ),
      );
    if (node.type === "action")
      detail.append(
        el(
          "p",
          "",
          `${label(node.status)} · ${node.authorization || "No authorization recorded."}`,
        ),
      );
    const related = graphLinks.filter(
      (link) => link.from === id || link.to === id,
    );
    detail.append(
      el(
        "span",
        "detail-label",
        `${related.length} connected relationship${related.length === 1 ? "" : "s"}`,
      ),
    );
    const relations = el("ul", "node-relations");
    related.forEach((link) => {
      const target = nodeMap.get(link.from === id ? link.to : link.from);
      const item = el("li");
      item.append(
        el("span", "", `${link.from === id ? "→" : "←"} ${link.relation}: `),
      );
      const button = el("button", "", target.label);
      button.type = "button";
      button.addEventListener("click", () => selectNode(target.id));
      item.append(button);
      relations.append(item);
    });
    if (!related.length)
      relations.append(el("li", "", "No explicit relationships recorded."));
    detail.append(relations);
  }
  function renderGraph() {
    const groups = ["source", "metric", "finding", "action"];
    const colors = ["#9b8663", "#6d846d", "#ba745d", "#6d7c90"];
    const columns = groups.map((type) =>
      nodes.filter((node) => node.type === type),
    );
    const height = Math.max(
      310,
      Math.max(1, ...columns.map((column) => column.length)) * 63 + 65,
    );
    const svg = svgEl("svg", {
      viewBox: `0 0 660 ${height}`,
      role: "group",
      "aria-label":
        "Knowledge graph. Use Tab to select sources, metrics, findings, and actions.",
    });
    const positions = new Map();
    columns.forEach((column, col) => {
      svg.append(
        svgEl(
          "text",
          { x: col * 162 + 23, y: 29, class: "graph-col-label" },
          `${groups[col].toUpperCase()}S`,
        ),
      );
      column.forEach((node, index) =>
        positions.set(node.id, { x: 12 + col * 162, y: 51 + index * 63 }),
      );
    });
    graphLinks.forEach((link) => {
      const a = positions.get(link.from);
      const b = positions.get(link.to);
      const forward = a.x <= b.x;
      const ax = a.x + (forward ? 143 : 0);
      const bx = b.x + (forward ? 0 : 143);
      const mid = (ax + bx) / 2;
      const path = svgEl("path", {
        d: `M${ax} ${a.y + 22} C${mid} ${a.y + 22},${mid} ${b.y + 22},${bx} ${b.y + 22}`,
        class: "graph-line",
      });
      path.append(
        svgEl(
          "title",
          {},
          `${nodeMap.get(link.from).label} → ${link.relation} → ${nodeMap.get(link.to).label}`,
        ),
      );
      svg.append(path);
      lineElements.push({ element: path, link });
    });
    nodes.forEach((node) => {
      const position = positions.get(node.id);
      const group = svgEl("g", {
        class: "graph-node",
        transform: `translate(${position.x},${position.y})`,
        role: "button",
        tabindex: "0",
        "aria-label": `${label(node.type)}: ${node.label}`,
        "aria-pressed": "false",
      });
      group.append(
        svgEl("title", {}, node.label),
        svgEl("rect", { width: 143, height: 44, rx: 6 }),
        svgEl("circle", {
          cx: 11,
          cy: 14,
          r: 2.5,
          fill: colors[groups.indexOf(node.type)],
        }),
      );
      const short =
        String(node.label).length > 25
          ? `${String(node.label).slice(0, 23)}…`
          : node.label;
      group.append(
        svgEl("text", { x: 20, y: 17 }, short),
        svgEl("text", { x: 11, y: 33, class: "node-id" }, node.id),
      );
      group.addEventListener("click", () => selectNode(node.id));
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectNode(node.id);
        }
      });
      svg.append(group);
      nodeElements.set(node.id, group);
    });
    if (nodes.length) byId("graph-container").append(svg);
    else
      byId("graph-container").append(
        el("p", "empty-state", "No connected knowledge recorded."),
      );
  }
  renderGraph();
  const history = list(payload.history).length
    ? list(payload.history)
    : [payload.baseline || current];
  const snapshots = list(payload.snapshots).length
    ? list(payload.snapshots)
    : history.map((snapshot, index) => ({
        id: index === 0 ? "Baseline" : `Snapshot ${index + 1}`,
        captured_at: snapshot.captured_at,
        sha256: "",
      }));
  [...snapshots].reverse().forEach((snapshot, index) => {
    const item = el("li", "history-item");
    const time = el("time", "", date(snapshot.captured_at));
    if (!Number.isNaN(new Date(snapshot.captured_at).getTime()))
      time.dateTime = snapshot.captured_at;
    item.append(
      el("strong", "", snapshot.id || `Snapshot ${snapshots.length - index}`),
      time,
    );
    if (snapshot.sha256)
      item.append(el("code", "", `SHA-256 ${snapshot.sha256}`));
    if (index === snapshots.length - 1)
      item.append(el("span", "quiet-badge", "Reference baseline"));
    byId("history-list").append(item);
  });
  metrics.forEach((metric) => {
    const option = el("option", "", metric.label);
    option.value = metric.id;
    byId("evolution-metric").append(option);
  });
  function chartEmpty(title, message) {
    const box = el("div", "chart-empty");
    box.append(
      el("span", "chart-empty-symbol", "⌁"),
      el("strong", "", title),
      el("p", "", message),
    );
    byId("evolution-chart").append(box);
  }
  function renderChart() {
    const target = byId("evolution-chart");
    target.replaceChildren();
    const metric = metrics.find(
      (item) => item.id === byId("evolution-metric").value,
    );
    if (!metric) {
      chartEmpty(
        "No metric recorded",
        "Measurements will appear when a reference snapshot is captured.",
      );
      return;
    }
    const change = changes.find((item) => item.metric_id === metric.id);
    if (snapshots.length < 2 || history.length < 2) {
      chartEmpty(
        "A baseline, not a trend.",
        "One recorded snapshot establishes the reference. A later compatible measurement is needed to show evolution.",
      );
      return;
    }
    if (!change || change.comparable !== true) {
      chartEmpty(
        "These measurements are not comparable.",
        change?.reason ||
          "A verified comparison with a compatible measurement basis has not been recorded.",
      );
      return;
    }
    const duration = (item) =>
      item?.period_start && item?.period_end
        ? new Date(item.period_end).getTime() -
          new Date(item.period_start).getTime()
        : NaN;
    const referenceDuration = duration(metric);
    const points = history
      .map((snapshot) => {
        const measurement = list(snapshot.metrics).find(
          (item) => item.id === metric.id,
        );
        const compatible = Boolean(
          measurement &&
            Number.isFinite(measurement.value) &&
            measurement.unit === metric.unit &&
            measurement.comparability_key === metric.comparability_key &&
            Number.isFinite(referenceDuration) &&
            referenceDuration >= 0 &&
            duration(measurement) === referenceDuration &&
            !Number.isNaN(new Date(snapshot.captured_at).getTime()),
        );
        return {
          captured_at: snapshot.captured_at,
          metric: measurement,
          compatible,
        };
      })
      .sort((a, b) => new Date(a.captured_at) - new Date(b.captured_at));
    const compatiblePoints = points.filter((point) => point.compatible);
    if (compatiblePoints.length < 2) {
      chartEmpty(
        "More compatible data is needed.",
        "At least two numeric measurements with the same unit and comparison basis are required.",
      );
      return;
    }
    const values = compatiblePoints.map((point) => point.metric.value);
    const min = Math.min(0, ...values);
    const max = Math.max(1, ...values);
    const range = max - min || 1;
    const width = 530;
    const height = 210;
    const x = (index) => 48 + (index * 430) / (points.length - 1);
    const y = (value) => 155 - ((value - min) / range) * 115;
    const svg = svgEl("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": `${metric.label}: ${points.map((point) => `${date(point.captured_at)}, ${point.compatible ? valueWithUnit(point.metric) : "gap: unavailable or incompatible measurement"}`).join("; ")}`,
      class: "chart-svg",
    });
    [0, 0.5, 1].forEach((fraction) => {
      const value = min + range * fraction;
      svg.append(
        svgEl("line", {
          x1: 48,
          x2: 480,
          y1: y(value),
          y2: y(value),
          class: "chart-grid",
        }),
        svgEl(
          "text",
          {
            x: 35,
            y: y(value) + 3,
            class: "chart-label",
            "text-anchor": "end",
          },
          number(value),
        ),
      );
    });
    let segment = [];
    const flushSegment = () => {
      if (segment.length > 1)
        svg.append(
          svgEl("polyline", {
            points: segment.join(" "),
            fill: "none",
            stroke: "#668253",
            "stroke-width": 2,
          }),
        );
      segment = [];
    };
    points.forEach((point, index) => {
      if (point.compatible)
        segment.push(`${x(index)},${y(point.metric.value)}`);
      else flushSegment();
    });
    flushSegment();
    points.forEach((point, index) => {
      if (point.compatible) {
        const dot = svgEl("circle", {
          cx: x(index),
          cy: y(point.metric.value),
          r: 4,
          fill: "#668253",
          stroke: "white",
          "stroke-width": 2,
        });
        dot.append(
          svgEl(
            "title",
            {},
            `${date(point.captured_at)}: ${valueWithUnit(point.metric)}`,
          ),
        );
        svg.append(dot);
        if (index === 0 || index === points.length - 1)
          svg.append(
            svgEl(
              "text",
              {
                x: x(index),
                y: y(point.metric.value) - 12,
                class: "chart-value",
                "text-anchor": "middle",
              },
              valueWithUnit(point.metric),
            ),
          );
      } else {
        svg.append(
          svgEl("line", {
            x1: x(index),
            x2: x(index),
            y1: 40,
            y2: 155,
            stroke: "#b9c2ae",
            "stroke-dasharray": "3 4",
          }),
          svgEl(
            "text",
            {
              x: x(index),
              y: 28,
              class: "chart-label",
              "text-anchor": "middle",
            },
            "gap",
          ),
        );
      }
      if (index === 0 || index === points.length - 1)
        svg.append(
          svgEl(
            "text",
            {
              x: x(index),
              y: 185,
              class: "chart-label",
              "text-anchor": index === 0 ? "start" : "end",
            },
            date(point.captured_at),
          ),
        );
    });
    target.append(svg);
    const gaps = points.filter((point) => !point.compatible);
    if (gaps.length)
      target.append(
        el(
          "p",
          "chart-gap-note chart-note",
          `Gap at ${gaps.map((point) => date(point.captured_at)).join(", ")}: measurement unavailable or incompatible. Capture positions are retained; lines stop at each gap.`,
        ),
      );
  }
  byId("evolution-metric").addEventListener("change", renderChart);
  if (!metrics.length) byId("evolution-metric").disabled = true;
  renderChart();
  changes.forEach((change) => {
    const metric = metrics.find((item) => item.id === change.metric_id);
    const row = el("div", "change-row");
    row.append(
      el("strong", "", change.label || metric?.label || change.metric_id),
      el(
        "span",
        "",
        `${number(change.before)} → ${number(change.after)}${metric?.unit ? ` ${metric.unit}` : ""}`,
      ),
      el(
        "span",
        change.comparable ? "" : "not-comparable",
        change.comparable
          ? `Recorded change: ${change.delta > 0 ? "+" : ""}${number(change.delta)}`
          : `Not comparable: ${change.reason || "Measurement basis is incompatible."}`,
      ),
    );
    byId("changes-list").append(row);
  });
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!visible) return;
        document.querySelectorAll(".nav-list a").forEach((anchor) => {
          const active =
            anchor.getAttribute("href") === `#${visible.target.id}`;
          anchor.classList.toggle("active", active);
          if (active) anchor.setAttribute("aria-current", "location");
          else anchor.removeAttribute("aria-current");
        });
      },
      { rootMargin: "-5% 0px -45% 0px", threshold: [0, 0.1, 0.5] },
    );
    document
      .querySelectorAll("main>.section")
      .forEach((section) => observer.observe(section));
  }
})();
