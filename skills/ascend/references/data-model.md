# Evidence data model and local runtime

ASCEND V1 stores an explicit, dated account of a project using `schema_version: 1`. The runtime validates structure, links, and history integrity. It does **not** certify that a source is truthful, that a claim is supported by the content of that source, that an authorization string records real consent, or that an action worked. The assistant and human reviewer remain responsible for those judgments.

## Input snapshot

An input is UTF-8 JSON with `schema_version: 1`. Both its original bytes and its canonical stored serialization must fit within 16 MiB. Compact input can grow during indentation; the runtime validates that stored size before creating a workspace or lock. It also prepares and bounds the manifest and pointer before any capture writes, so a successful capture remains readable by the same reader limits. JSON duplicate keys, NaN, infinity, unknown fields, and missing required fields fail validation. Identifiers contain 1–96 ASCII letters, digits, periods, colons, underscores, or hyphens and start with a letter or digit. The project, sources, metrics, findings, benchmarks, and actions have globally unique IDs within each snapshot. Reuse an object's ID across snapshots when its meaning remains the same.

Every snapshot contains all of the following fields. Empty arrays are valid when no evidence exists; do not fill them with invented evidence.

| Field | Required content |
| --- | --- |
| `schema_version` | Integer `1`, not boolean. |
| `captured_at` | ISO 8601 UTC timestamp, such as `2026-10-25T12:00:00Z` or with `+00:00`. Optional fractional seconds contain at most six digits. |
| `project` | `id`, `name`, `domain`, `summary`, `objective`, `constraints` (array of strings), `brand: {"accent":"#89cf65"}`, and `simulation` (boolean). |
| `sources` | Objects with `id`, `title`, `kind`, `locator`, `captured_at`, `status`, and optional `note`. |
| `coverage` | Objects with `area`, `status`, `source_ids`, and `note`. |
| `metrics` | Objects with `id`, `label`, `value`, `unit`, `period_start`, `period_end`, `source_ids`, and `comparability_key`. |
| `findings` | Objects with `id`, `title`, `detail`, `kind`, `severity`, `confidence`, `source_ids`, `metric_ids`, and `verification`. |
| `benchmarks` | Objects with `id`, `label`, `source_ids`, `comparison`, `limitations`, and `simulated` (boolean). |
| `actions` | Objects with `id`, `title`, `rationale`, `finding_ids`, `status`, `cost`, `expected_outcome`, `verification`, and `authorization` (string or null). |
| `links` | Objects with `from`, `to`, and `relation`; both endpoints reference existing IDs, including the project ID. |

Strings are nonempty, except `coverage.note` and optional `source.note`, which may be empty. A locator is a provenance label or URL, never an instruction: the runtime does not open it, execute it, or fetch its contents. Avoid placing secrets, customer records, credentials, private machine paths, or unnecessary personal data in snapshots. The dashboard exports the snapshot content, including source metadata, to the local browser.

### Provenance and coverage

- `source.kind`: `provided`, `connector`, `file`, `web`, or `simulation`.
- `source.status`: `available` or `unavailable`. Source timestamps cannot be later than the snapshot timestamp. `available` means the author recorded access to the evidence, not that the runtime accessed it.
- `coverage.status`: `examined`, `partial`, `unavailable`, or `not_applicable`. `examined` needs an available source. Area names must be unique. An area marked unavailable can have no source IDs; its note should explain the gap.
- Every reference array rejects nonexistent or duplicate IDs. A valid reference confirms existence, not substantive support.

### Metrics and comparison

`value` is a finite number or null; booleans are rejected. A non-null value requires an available source. Dates use `YYYY-MM-DD`; the start cannot follow the end, and the end cannot follow the snapshot date. Store the measurement's actual interval rather than guessing a standard period.

Use a descriptive `comparability_key` for the definition and scope, for example `qualified-store-sessions:v1:exclude-owner-and-bots`. Keep the same ID when the metric is the same; change the comparability key when its measurement definition or scope changes.

The runtime compares baseline and current values by ID only when:

1. The metric appears in both snapshots and both values are known.
2. `unit` and `comparability_key` match exactly.
3. The inclusive measurement period durations match.

It emits an absolute `delta`, never a relative percentage. A zero baseline therefore produces a valid absolute change without division by zero. Missing values are not zero. Missing metrics, changed definitions, changed units, unequal periods, and numeric overflow produce `comparable: false`, `delta: null`, and a reason. The union of baseline and current metric IDs is represented, including removed and new metrics.

These are structural comparability checks. They do not establish equal seasonality, market conditions, attribution, statistical significance, or causality. A human or assistant must assess those limits before interpreting the change. Historical charts must preserve gaps and comparability limits.

### Findings, benchmarks, and actions

| Field | Allowed values or rule |
| --- | --- |
| `finding.kind` | `observed`, `hypothesis`, `unknown`. An observed claim requires at least one available source. |
| `finding.severity` | `red`, `yellow`, `green`, `grey`. Unknown findings must be grey. |
| `finding.confidence` | `high`, `medium`, `low`; separate from priority. |
| `finding.verification` | A concrete next check, or the procedure supporting the observation. |
| `benchmark.source_ids` | At least one available source. Simulated source references require `simulated: true`. |
| `benchmark.limitations` | Describe relevance, missing context, and comparison limits. The field's presence does not certify its quality. |
| `action.status` | `proposed`, `authorized`, `in_progress`, `completed`, `blocked`, `cancelled`. |
| `action.authorization` | `authorized`, `in_progress`, and `completed` require a nonempty authorization reference; other statuses may use null. |

The runtime never performs actions and never marks one completed. It stores the supplied status. The assistant must independently verify any declared completion and record the supporting evidence before preparing an input. An authorization string and `--authorize-write` flag are acknowledgements; neither is a technical access control or proof of consent. Approval for local storage does not grant approval for business changes, connectors, publishing, messaging, spending, or Git operations.

## Local storage

Choose a project-specific workspace. An existing project directory is supported; initialization preserves its existing files and refuses an existing `.ascend` path. The workspace's immediate parent must already exist. Symbolic links and Windows junctions at managed paths are refused.

```text
<workspace>/
  .ascend.lock                  Present only while a writer holds the lock
  .ascend/
    CURRENT                     Atomic pointer with the active manifest digest
    generations/
      g-000001-<random>/
        snapshot.json           Original baseline; never updated by the runtime
        manifest.json
      g-000002-<random>/
        snapshot.json           Next dated state
        manifest.json
  dashboard/
    index.html
    styles.css
    app.js
```

The manifest records the actor, project ID, parent generation and manifest SHA256, and complete snapshot index. Each index entry contains a snapshot ID, generation, timestamp, SHA256, and previous snapshot SHA256. No local absolute paths are embedded in the manifests. The capture ID identifies the stored observation; project object IDs identify entities within that observation.

Initialization commits a staged store by directory rename. Captures stage a new immutable generation, flush new files, then atomically replace `CURRENT` as the final commit. Before capture, render, or serve, the runtime verifies the full manifest ancestry and the snapshots' digests, structure, project continuity, and chronology. A capture must retain `project.id` and `project.simulation` and strictly advance `captured_at`. Simulated and real histories cannot be mixed. All prior snapshot entries must remain unchanged.

Writers use an exclusive `.ascend.lock` and recheck the state after acquiring it. They fail instead of waiting indefinitely or overwriting another writer. A capture's serialized artifacts are prepared before acquiring the lock; if the active pointer changed in the meantime, the capture fails and must be rerun against the new state. Normal I/O failures before the pointer commit remove the new staged generation and retain the old active state. Dashboard rendering stages three files, preserves the prior dashboard in a temporary backup during the directory switch, and restores it if the switch raises an error.

An existing nonempty `dashboard` is considered generated output only when `index.html` starts with the exact `<!-- ASCEND-GENERATED-DASHBOARD v1 -->` marker followed by a newline. The renderer adds this marker to every generated index. Filenames alone do not establish ownership: an existing user `index.html`, even accompanied only by `styles.css` and `app.js`, is preserved and rendering fails before taking a write lock. Existing dashboards with other files are also refused. A missing or empty dashboard can be populated. The server requires the generated marker before starting, while its URL whitelist independently blocks any additional files. The marker prevents accidental adoption of user content; it is not an authenticated signature. Legacy prototype dashboards without the marker must be deliberately preserved or regenerated in a fresh workspace; ASCEND does not silently adopt them.

The runtime's immutability is an append-only application behavior, not operating-system write protection. SHA256 detects accidental corruption or edits that leave inconsistent hashes; it is **not** a signature against an attacker who can rewrite the entire store and recompute hashes. No crash/power-loss durability guarantee is made. An interrupted process may leave a lock, pending generation, or dashboard backup. Do not automatically remove these: inspect them, retain a backup, verify the active store, and recover deliberately. A damaged active history fails closed.

The 10,000-capture validation ceiling is a defensive upper guard, not a scalability claim. Each manifest repeats the complete index and verification reads the full ancestry; total index storage grows quadratically with capture count. This prototype targets modest local histories. A later storage version will need compact manifests or a database before large-scale use.

## Commands

Python 3.11 or newer is required; there are no third-party runtime dependencies. Run commands from the repository root, adjusting paths for an installed skill. `--actor` records which assistant or operator prepared a capture; it does not authenticate that actor.

```sh
python skills/ascend/scripts/ascend.py validate evidence.json
python skills/ascend/scripts/ascend.py init evidence.json --workspace ./project-state --actor "Claude Code" --authorize-write
python skills/ascend/scripts/ascend.py capture followup.json --workspace ./project-state --actor "Codex" --authorize-write
python skills/ascend/scripts/ascend.py verify --workspace ./project-state
python skills/ascend/scripts/ascend.py summary --workspace ./project-state
python skills/ascend/scripts/ascend.py summary --workspace ./project-state --format markdown
python skills/ascend/scripts/ascend.py inspect --workspace ./project-state --id finding-example
python skills/ascend/scripts/ascend.py render --workspace ./project-state --authorize-write
python skills/ascend/scripts/ascend.py serve --workspace ./project-state --port 8765
```

`validate`, `verify`, `summary`, and `inspect` are read-only. Inputs are validated before the runtime creates or changes state. Missing write acknowledgement, invalid input, invalid chronology, and a corrupted store prevent writes. Validation exits 0 on success and 2 on rejected input or an I/O error. `serve` blocks until interrupted and prints the actual port; port 0 selects a free local port for tests. No command runs source code, shells, external connectors, installs packages, creates Git commits, or changes a business system.

### Assistant context retrieval

Resume a project with `summary`, then use `inspect --id <ID>` for the records needed to answer the current question. Both commands call the same full ancestry and digest verification as `verify`, scope their reads to the named workspace, and create no files, directories, or locks. Missing workspaces, corrupt histories, and unknown current IDs exit 2 without partial context output.

`summary` returns JSON by default. Use `--format markdown` for compact readable sections and tables presenting the same bounded facts without JSON envelopes: actual periods, comparison reasons, explicit unknown values, priority separate from confidence, declared authorization, and counts of shown and omitted records. Text originating in project records is escaped for Markdown tables. The JSON response `schema_version: 1` is separate from the snapshot schema. It includes project identity, objective, constraints, domain, simulation marker, baseline/current capture IDs and timestamps, source and coverage status counts, coverage gaps, current metrics with measurement periods and baseline comparison reasons, prioritized findings, pending actions with declared authorization status, and context pointers. It excludes full snapshots, source contents, and historical records. A missing or empty coverage declaration does not mean the project was exhaustively examined. Source counts and the simulation flag remain supplied declarations.

List envelopes use `{"items": [...], "total": N, "omitted": M}`. Each includes at most 10 items; this also applies to nested source, metric, and finding reference lists and project constraints. Summary text fields are capped at 600 characters with a visible truncation marker. Full current record details are available through `inspect`; the summary points to the verified current snapshot for complete declared coverage and omitted IDs. Findings sort by severity (red, yellow, grey, green), then ID. Pending actions exclude completed and cancelled entries and sort by the highest priority of their referenced findings, then ID. Confidence remains a separate field and does not change this order. These are deterministic presentation rules, not a causal diagnosis or an urgency score computed from the business.

Current metrics retain actual periods, units, IDs, source references, baseline measurement metadata, and the existing structural comparison result. Removed metric comparisons are shown separately. Unknown values remain null; missing or incompatible metrics keep explicit reasons. Authorization references indicate only what the snapshot declares; `consent_verified_by_runtime` is always false. The assistant must still establish actual consent from the conversation.

`inspect` returns one current record's type, ID, complete content, current capture identity, and explicit linked neighbors with minimal labels. It supports project, source, metric, finding, benchmark, and action IDs. In addition to `links`, it exposes incoming and outgoing `source_ids`, `metric_ids`, and `finding_ids` references, and incoming coverage source references, even when `links` is empty. Relationships remain recorded relationships; the command neither invents edges nor certifies evidentiary support. Historical-only IDs are unknown in this interface. `inspect` intentionally includes full requested content and neighbors; select IDs from the bounded summary before retrieving details.

## Dashboard export and server boundary

The renderer injects exactly one complete block at `{{ASCEND_DATA}}` in `assets/dashboard/template.html`:

```html
<script type="application/json" id="ascend-data">{"current":{}}</script>
```

The actual JSON payload contains:

```text
current       latest snapshot
baseline      first snapshot
history       all snapshots, chronological order
changes       [{metric_id,label,before,after,delta,comparable,reason}]
snapshots     [{id,captured_at,sha256}]
generated_at  UTC render timestamp
```

The JSON encoder escapes `<`, `>`, `&`, and Unicode line separators, including a hostile closing script tag. Client code must parse the block's `textContent`, render untrusted strings as text, and restrict any external evidence links to safe HTTP(S) URLs. CSS and JavaScript are local files. The template must not wrap the placeholder inside another script element.

The server binds **only `127.0.0.1`**, accepts only its loopback hostnames and active port, and serves only `/`, `/index.html`, `/styles.css`, and `/app.js`. It refuses directory listings, other files, traversal, symbolic links, and junctions. It never serves `.ascend`, project source files, or the workspace root. CSP blocks network connections, remote scripts, inline scripts, framing, and base-URL changes; the report uses no remote assets. Access logging is disabled to avoid logging private query strings. Other local users/processes and browser extensions may still access a loopback server; this is a local preview, not an authenticated multi-user service.

The dashboard is a rendered snapshot. A new capture requires an explicit new `render` and browser reload. It is neither live connector synchronization nor an autonomous scheduler. Weekly follow-up remains a deliberate skill invocation in this version.
