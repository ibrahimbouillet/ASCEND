# Compatibility and boundaries

The shared `SKILL.md` uses the common name/description frontmatter and relative references. It does not require host-specific variables, automatic shell injection, an MCP server, or a named model. Optional `agents/openai.yaml` supplies Codex interface metadata.

## Intended installations

| Host | Project location | Personal location |
| --- | --- | --- |
| Codex | `.agents/skills/ascend/` | `~/.agents/skills/ascend/` |
| Claude Code | `.claude/skills/ascend/` | `~/.claude/skills/ascend/` |

Use the V1 installer described in [INSTALL.md](../INSTALL.md), or copy `skills/ascend/` as a complete folder. Do not copy the whole repository into a single skill folder. Filesystem installation, model/tool permissions, and native host execution are separate checks.

Official documentation consulted on 2026-10-25: [OpenAI skills](https://learn.chatgpt.com/docs/build-skills), [Claude Code skills](https://code.claude.com/docs/en/skills). Their discovery rules can change. V1 ships a versioned standalone skill and local installer, not a submitted marketplace plugin.

## Runtime

Python 3.11+ is needed only for the optional helper, which uses the standard library. The skill can still diagnose supplied material through the host's tools without running that helper. Its dashboard uses local HTML, CSS, and JavaScript, with no external asset requests.

The helper accepts curated snapshots. It does not access Shopify or Instagram, browse international sources, run project changes, connect accounts, call an LLM, or schedule reviews. Those operations belong to the host agent and require available tools and user authorization. The fixtures do not imply a connector has been tested.

## Shared state

Both hosts can read the same user-authorized workspace. The helper serializes writes with a local lock; this is not a distributed synchronization service. Host chat memory and account credentials are not shared by the skill. Before switching hosts, inspect the latest capture, evidence, pending actions, and existing approvals.

Integrity digests detect accidental changes relative to stored records. They are not signatures, independent attestations, source authentication, or a substitute for human approval.

## Validation status

See [VALIDATION_V1.md](VALIDATION_V1.md) and the earlier [VALIDATION.md](VALIDATION.md) for executed checks. Filesystem installation, local runtime, agent behavior, native discovery, live integrations, and business impact are separate claims.

The native Codex CLI recognized the project-local skill in an isolated smoke attempt, but its execution policy denied the subsequent read commands. Full native use remains unverified. Claude Code's CLI was not found on PATH in this development environment.
