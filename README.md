# ASCEND

**AI Project Intelligence & Optimization**

*Understand. Strategize. Evolve.*

ASCEND is an experimental skill for understanding a project's real state, investigating relevant comparisons, planning improvements, and reviewing progress against a dated baseline. Its intended hosts are Claude Code and OpenAI Codex.

**Status: v0.1 development preview.** The local helper and fictional demonstration can be exercised today. Native host discovery, live service connectors, cross-domain reliability, and real business outcomes require separate validation. No sales or project-success guarantee is made.

## What happens in an ASCEND session

1. Explain the proposed collection and obtain the required authorization.
2. Examine the available project evidence in read-only mode and report coverage gaps.
3. With local write approval, preserve a baseline and linked findings, sources, measures, and actions.
4. Investigate comparable evidence and present prioritized, conditional recommendations.
5. Carry out only approved actions, verify their completion, and review new measurements on subsequent requests.

An optional local dashboard presents the same structured records. It includes evidence, audit priorities, a knowledge graph, proposed actions, and history. It does not approve changes or publish project data.

## Try the fictional project

Requires Python 3.11+; the shipped helper uses only the standard library. Run from this repository root:

```console
python -c "from pathlib import Path; Path('.local').mkdir(exist_ok=True)"
python skills/ascend/scripts/ascend.py validate examples/atelier-solstice/baseline.json
python skills/ascend/scripts/ascend.py init examples/atelier-solstice/baseline.json --workspace .local/atelier-solstice --actor demo --authorize-write
python skills/ascend/scripts/ascend.py capture examples/atelier-solstice/followup.json --workspace .local/atelier-solstice --actor demo --authorize-write
python skills/ascend/scripts/ascend.py render --workspace .local/atelier-solstice --authorize-write
python skills/ascend/scripts/ascend.py serve --workspace .local/atelier-solstice --port 8765
```

Open `http://127.0.0.1:8765` while the server runs. The data represents **Atelier Solstice**, a fictional small clothing business. Both captures are synthetic; orders remain zero. This demonstrates honest tracking rather than a simulated commercial success.

`--authorize-write` records the operator's acknowledgement of already-granted local write permission. The helper cannot establish that a human consented. Its data validation does not establish that an assertion is true.

## Use the skill in an agent

The reusable package is `skills/ascend/`. Copy that entire folder to the chosen host's skill location, preserving its supporting files. Review an existing installation before replacing it.

| Host | Project-local destination | Invocation |
| --- | --- | --- |
| Codex CLI / IDE | `.agents/skills/ascend/` | `$ascend` |
| Claude Code | `.claude/skills/ascend/` | `/ascend` |

Example request:

> Use ASCEND to diagnose this project. You may inspect the supplied files in read-only mode. Explain what you examined, distinguish evidence from hypotheses, and propose the next useful steps. Ask before creating a local workspace or changing the project.

These locations and invocation forms follow the [official OpenAI guidance](https://learn.chatgpt.com/docs/build-skills) and [Claude Code guidance](https://code.claude.com/docs/en/skills). This preview ships a shared standalone skill; marketplace/plugin distribution is future work. See [compatibility and limits](docs/COMPATIBILITY.md).

## Development and evaluation

```console
python -m unittest discover -s tests -v
```

Optional UI checks require Playwright and a locally installed Chromium. With both demonstration servers running, `node tests/browser_smoke.cjs` checks desktop/mobile behavior; `node tests/browser_edgecases.cjs` creates and cleans isolated test workspaces. Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` when the installed browser is outside Playwright's default location.

Behavioral scenarios in `evals/evals.json` cover commerce, learning, and research. Evaluate the same requests with and without the skill. Measure diagnosis quality, authorization handling, correct execution, and real project outcomes separately. See [evaluation protocol](docs/EVALUATION.md) and [architecture](docs/ARCHITECTURE.md).

The first target is at least 70% of behavioral scenarios passing within each tested project family, with no critical permission or fabricated-evidence failure. A small synthetic exercise does not establish this target at production scale.

## Project layout

```text
skills/ascend/                 Installable skill, references, helper, dashboard assets
examples/atelier-solstice/     Fictional brief and dated captures
evals/                        Behavioral prompts and input material
tests/                        Deterministic helper checks
docs/                         Architecture, evaluation, compatibility, validation
```

The licensing and public release policy will be decided before public distribution.
