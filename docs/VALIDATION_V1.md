# ASCEND 1.0.0 validation — 2026-10-25

V1 establishes a versioned installation/distribution contract and a compact project-context interface. It retains the evidence and authorization boundaries of the first preview. A stable distribution version does not establish business success or universal project efficacy.

## Local verification

Environment: Windows, Python 3.14.7. The complete standard-library suite passed **113/113 tests in 67.749 seconds**, with no failures or skips:

| Area | Tests | Coverage |
| --- | --- | --- |
| Existing runtime and shipped example | 39 | Evidence structure, baseline preservation, writes/rollback, integrity, local server and dashboard payload |
| Agent context | 13 | Read-only summary/inspection, unknowns, comparison definitions, priority/confidence separation, omissions, safe readable output |
| Installer | 35 | Both hosts, user/project scopes, dry run, verification, customization preservation, upgrades/backups, downgrade refusal and rollback |
| Release | 26 | Deterministic builds, checksums, payload manifests, license retention, version consistency and unsafe/tampered archive rejection |

Skill Creator's structural validation passed. It checks skill structure, not decision quality or host-specific behavior.

## Extracted-package round trip

The actual V1 ZIP was built and verified, then extracted into a new directory. Its own installer performed a both-host dry run, installation, verification, and idempotent repeat using a temporary home path with spaces. No real user-home installation was changed.

Both installed copies retained the MIT notice. Running the installed runtime did not change the installed payload hashes. The Codex-location runtime initialized a fictional project, captured its follow-up, returned JSON and readable Markdown context, inspected a finding, rendered the dashboard, and verified history. The Claude-location runtime read the same state and returned an identical JSON context.

The package's own builder reproduced a byte-identical ZIP from the extracted package. The payload contains 16 files plus its embedded manifest; source tests, eval data, local snapshots, credentials, and caches are excluded. Versioned outputs refuse replacement with different bytes.

This demonstrates filesystem installation and helper execution for both target layouts. It does **not** mean a Claude model or native Claude Code process was run.

## Independent checks

A separate reviewer ran the initial 59 installer/release tests and independently exercised actual build, verification, extraction, both-host install/verify, hash correspondence, and idempotence. Mixed-host failure injection restored prior files and removed partial installation; downgrade preflight preserved existing bytes. No blocker was demonstrated in that review. The later license/version checks and readable Markdown changes passed the final full suite and round trip described above.

The preview's 13 browser checks covered desktop/mobile interaction, explicit unknowns, read-only actions, source/graph navigation, hostile text, unequal periods, and visible historical gaps. V1 changes the displayed version but retains those dashboard behaviors. See [the initial validation record](VALIDATION.md) for detailed observed failures and fixes.

## Context size observation

On the supplied fictional two-capture store, Python `json.dumps` produced 33,884 characters for the history, 18,371 for the current snapshot, and 12,814 for bounded JSON context. Readable Markdown context contained 8,605 characters before the CLI's trailing newline. These are representation-specific character counts, not token, speed, or universal efficiency benchmarks. Important unknowns, evidence IDs, measurement periods, and authorization limits remain visible; omitted records require targeted inspection.

## GitHub release checks

The release procedure requires CI on Windows/Linux with Python 3.11/3.14, a matching immutable tag, downloadable ZIP/manifest/checksums, and verification after downloading from GitHub. The published release notes link the actual CI result and state the delivery checks performed. This document records local results; a workflow file alone is not evidence that CI ran.

## Scope and limits

Installation follows the standalone directories documented by [OpenAI](https://learn.chatgpt.com/docs/build-skills) and [Claude Code](https://code.claude.com/docs/en/skills). The installer does not modify host settings, credentials, connectors, or project configuration. Installed `SKILL.md` applies when the workflow is relevant and cannot override host instructions or user permissions.

The previous native Codex smoke recognized the skill but execution policy blocked subsequent read commands. That result remains partial; the CLI's zero exit code was not a completed assessment. Claude Code's CLI was not found on PATH. Full native host execution, live Shopify/Instagram collection, real external benchmarking, broad held-out performance and a real-company pilot remain unverified.

Earlier paired synthetic cases showed limited expectation-level differences, with all cases passing in both configurations. V1 does not convert those smoke tests into proof of a 70% general success rate. The local history store still targets modest histories, with quadratic manifest-index storage and no publisher signatures or independently authenticated evidence.
