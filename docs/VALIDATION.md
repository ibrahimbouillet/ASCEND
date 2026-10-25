# Validation record — 2026-10-25

This records the first development preview, including observed failures and corrections. Passing synthetic checks does not establish real project success or broad cross-domain reliability.

## Implemented and exercised

- Shared ASCEND instructions and focused references, with Codex UI metadata.
- Standard-library local helper: validate, initialize, capture, verify, render, and serve.
- Immutable baseline and subsequent captures, evidence references, integrity checks, writer locks, and explicit local write acknowledgement.
- Local responsive dashboard with audit filters, evidence details, keyboard-navigable knowledge graph, action inspection, comparisons, history, and charts preserving unknowns and gaps.
- Two synthetic captures for Atelier Solstice. Sessions and views increase; orders remain zero and checkout starts remain unknown. A fictional drafting action has a fictional approval and completion artifact. No live business result is implied.

## Deterministic verification

Environment: Windows, Python 3.14.7, Node.js 24.21.0, Playwright 1.62.1, locally installed Chromium. Other operating systems and Python versions were not run.

| Check | Observed result |
| --- | --- |
| Full Python suite | 39/39 tests passed, 13.482 seconds |
| Desktop/mobile browser smoke | 10/10 checks passed |
| Adversarial browser cases | 3/3 checks passed |
| Browser console/runtime errors in these checks | None observed |
| External network requests in the smoke test | None observed |
| Skill Creator structural validator | Passed |
| Stored demo integrity | Two captures verified, including baseline and manifest ancestry |

The runtime tests cover preservation of existing files, missing authorization acknowledgement, invalid inputs, references, periods, concurrency, failed writes and rollback, altered history, unsafe source strings, and local server boundaries. The shipped demo is exercised through initialization, follow-up capture, and actual dashboard payload parsing.

Browser checks cover a 1440px desktop and 390px mobile viewport, simulation visibility, unknown values, filters, source expansion, graph keyboard interaction, read-only actions, zero-order charts, single-capture state, hostile strings, unequal periods, and an incompatible intermediate capture represented as a visible gap.

## Independent review and repairs

An independent code review reproduced three defects after the initial 33-test suite passed:

1. **Dashboard ownership:** filenames alone allowed replacement of a user's unrelated `dashboard/index.html`. Render and serve now require an ASCEND generated-index marker. Regression tests preserve both index-only and matching index/CSS/JS user directories. The reviewer independently confirmed the original content and complete workspace tree remain unchanged on rejection.
2. **Serialized size:** a valid 6,401,734-byte compact input expanded beyond the 16 MiB storage-read limit. Serialized snapshot, manifest, and pointer sizes are now checked before writes. The reviewer independently confirmed oversized initialization creates no workspace and oversized follow-up preserves a verifiable baseline.
3. **Historical gaps:** a chart previously filtered incompatible captures and connected the remaining points. Captures now retain their horizontal positions, incompatible points have visible explanations, and lines stop at gaps. The browser regression verifies no line crosses the missing measurement.

Integration also exposed an unavailable external comparison incorrectly stored as a benchmark; it is now an explicit coverage gap. A missing favicon caused browser errors and was replaced by a local inline icon.

## Agent behavioral smoke tests

Eight isolated executor runs formed four pairs: commerce, learning, research, and a commerce repeat after a targeted instruction revision. Executors loaded either the skill or no project-analysis skill and received the same raw inputs. A separate model evaluator graded the saved assessments; the evaluator was not blinded. Raw reports, expectations, grades, and benchmark data are retained in [evals/results/2026-10-25](../evals/results/2026-10-25/).

| Scenario | With ASCEND | Without ASCEND |
| --- | --- | --- |
| Commerce, initial | 9/10 expectations | 9/10 expectations |
| Learning | 8/8 | 7/8 |
| Research | 10/10 | 10/10 |
| Commerce, revised instruction and repeat | 10/10 | 9/10 |

The initial commerce answers both omitted an explicit future like-for-like comparison. ASCEND's instructions now ask the initialization proposal to specify measurement definitions and periods or equivalent acceptance conditions. The repeated ASCEND assessment included that detail. The learning baseline omitted explicit synthetic framing. Research produced a ceiling effect, with no observed score separation.

All cases pass the preliminary 70% expectation threshold in both configurations; **no case-level pass-rate advantage has been demonstrated**. Differences in individual expectations are limited evidence. Prompts state many constraints explicitly, only one raw case exists per family, and the repeat used a known case. These are smoke tests, not the held-out acceptance exam. No native software-project behavioral case has been evaluated yet.

Operational side-effect absence is partly executor-reported rather than backed by complete independent tool telemetry. Harness-required report/transcript artifacts were explicitly permitted and excluded from task mutations. Token and duration telemetry were not available and are recorded as null rather than zero. Raw executor transcripts are local evaluation artifacts; the committed evidence contains reports and grades with no private machine paths.

## Still unverified

An additional native Codex CLI smoke attempt used version `0.163.0-alpha.11.2`, an isolated project-local `.agents/skills/ascend` copy, an ephemeral read-only session, and no loaded user configuration. Invocation recognized ASCEND and resolved its supporting reference, but execution policy rejected the commands to read the fictional brief and workflow reference. The agent reported the gap and did not invent an assessment or claim initialization. CLI exit code zero therefore does **not** mean the project assessment succeeded. This is a partial native integration result, not an end-to-end pass. A sanitized [assessment and status](../evals/results/2026-10-25/native-codex/) are retained; raw logs with local paths remain excluded.

Claude Code's CLI was not found on PATH and was not run. Complete native use in both hosts, live Shopify/Instagram connectors, real external benchmarking, repeated held-out cross-domain performance, human assessment, and a real-project pilot remain unverified. The eventual target of 70% successful cases within each supported family has not been demonstrated at a representative scale. Licensing and public release policy remain to be decided.

The local store targets modest histories; its repeated manifest indexes have quadratic storage growth. Integrity hashes are consistency checks, not signatures. The helper cannot establish source truth, human consent, action effectiveness, or business causality.
