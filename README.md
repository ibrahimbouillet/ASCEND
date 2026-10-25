# ASCEND

**AI Project Intelligence & Optimization**

*Understand. Strategize. Evolve.*

Understand a project's real state, investigate evidence, choose useful improvements, and track progress against a dated baseline. ASCEND is a shared Agent Skill for **Claude Code and OpenAI Codex**, with an optional local dashboard and standard-library Python helpers.

**Current release: [v1.0.0](https://github.com/ibrahimbouillet/ASCEND/releases/tag/v1.0.0)** · [Installation](INSTALL.md) · [Validation](https://github.com/ibrahimbouillet/ASCEND/blob/v1.0.0/docs/VALIDATION_V1.md) · [MIT](LICENSE)

## Give the repository link to your coding agent

Copy this request into Codex or Claude Code in an environment that can read GitHub and manage local files:

> Install ASCEND from https://github.com/ibrahimbouillet/ASCEND using its latest stable GitHub release. Read and follow INSTALL.md, choose the installation for the coding agent you are running in, preserve existing skills, and verify the installation. Then use ASCEND for this project's analysis and progress reviews, following its SKILL.md. Tell me which version and location were installed. Installation does not authorize project changes or external account actions.

The agent should select a stable release rather than a moving development branch. If GitHub access or local installation is unavailable, it should explain the limit instead of claiming installation. Private repositories require authenticated read access. Ordinary chat without filesystem/skill support cannot create a persistent installation.

## Install V1 yourself

Requires Python 3.11+ and Git. Use a **new** checkout location:

```console
git clone --branch v1.0.0 --depth 1 https://github.com/ibrahimbouillet/ASCEND.git ASCEND-v1
cd ASCEND-v1
python scripts/install.py --host codex --scope user --dry-run
python scripts/install.py --host codex --scope user
python scripts/install.py --host codex --scope user --verify
```

Use `--host claude` or `--host both` as requested. For one project, use `--scope project --project <project-directory>`. See [INSTALL.md](INSTALL.md) for archive verification, access, updates, backups, and alternatives.

| Host | User installation | Project installation | Invoke |
| --- | --- | --- | --- |
| Codex | `~/.agents/skills/ascend/` | `.agents/skills/ascend/` | `$ascend` |
| Claude Code | `~/.claude/skills/ascend/` | `.claude/skills/ascend/` | `/ascend` |

Locations follow [OpenAI](https://learn.chatgpt.com/docs/build-skills) and [Claude Code](https://code.claude.com/docs/en/skills) guidance. Restart the host if the skill is not visible. Marketplace/plugin installation is not part of V1.

## What ASCEND does

1. Explains collection scope and obtains the required authorization.
2. Examines available evidence in read-only mode and records coverage gaps.
3. With local write approval, preserves a baseline, evidence links, measures, findings, and proposed actions.
4. Investigates relevant comparisons and proposes feasible improvements with verification criteria.
5. Supports approved actions and later reviews using compatible measurements.

The dashboard presents audit priorities, source evidence, a knowledge graph, actions, comparisons, and history using local assets. It cannot approve or execute changes. `summary` and `inspect` retrieve compact context and linked details without reading every historical snapshot.

Helpers do not collect Shopify/Instagram data or call an AI model. The host agent uses its available tools and services under user authorization; unavailable tools remain explicit gaps. V1 is the first versioned distribution. Broad project success and live integrations have not been established.

## Try the fictional project

From the source checkout, choose a new workspace:

```console
python -c "from pathlib import Path; Path('.local').mkdir(exist_ok=True)"
python skills/ascend/scripts/ascend.py init examples/atelier-solstice/baseline.json --workspace .local/atelier-solstice --actor demo --authorize-write
python skills/ascend/scripts/ascend.py capture examples/atelier-solstice/followup.json --workspace .local/atelier-solstice --actor demo --authorize-write
python skills/ascend/scripts/ascend.py summary --workspace .local/atelier-solstice --format markdown
python skills/ascend/scripts/ascend.py render --workspace .local/atelier-solstice --authorize-write
python skills/ascend/scripts/ascend.py serve --workspace .local/atelier-solstice --port 8765
```

Open `http://127.0.0.1:8765` while the server runs. Atelier Solstice is fictional: increased activity with zero orders and unknown checkout counts provides no commercial-success evidence. The source checkout contains examples; the small installable release omits evaluation data and snapshots.

## Checks and releases

From the source checkout (tests and evaluation data are not bundled in the installable archive):

```console
python -m unittest discover -s tests -v
python scripts/build_release.py --output .local/dist-1.0.0
python scripts/build_release.py --verify .local/dist-1.0.0/ascend-1.0.0.zip --checksums .local/dist-1.0.0/SHA256SUMS
```

Every published version has a Git tag, release notes, ZIP, payload manifest, and SHA256 checksums. Installation integrity, agent decisions, native host execution, and real project outcomes are separate claims. Read [V1 validation](https://github.com/ibrahimbouillet/ASCEND/blob/v1.0.0/docs/VALIDATION_V1.md), [initial experiments](https://github.com/ibrahimbouillet/ASCEND/blob/v1.0.0/docs/VALIDATION.md), and the [evaluation protocol](https://github.com/ibrahimbouillet/ASCEND/blob/v1.0.0/docs/EVALUATION.md).

The long-term target remains at least 70% successful cases within each tested family on representative held-out evaluations. Initial synthetic cases do not establish this target or guarantee a business result.

## Development

Runtime and installation need no third-party Python dependencies. Optional browser checks require Playwright and local Chromium. See [architecture](https://github.com/ibrahimbouillet/ASCEND/blob/v1.0.0/docs/ARCHITECTURE.md) and the validation record.

Copyright (c) 2026 Ibrahim Bouillet. Released under the [MIT license](LICENSE).
