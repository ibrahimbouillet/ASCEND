# Install ASCEND

This is the installation entry point for a coding agent given the repository URL. Install the shared skill into the host's supported skill directory; cloning the repository alone does not install it. Follow the host's permissions and higher-priority instructions. Installation does not authorize analysis, edits, spending, publishing, or external account actions beyond the user's request.

## Agent procedure from a repository link

1. Confirm this environment can read GitHub and manage skill files. Identify Codex or Claude Code; use both only when requested. Default to user scope for an ordinary request to install ASCEND for the agent; honor an explicitly requested project scope.
2. Resolve the latest **published stable** release. Do not choose a draft/prerelease, invent a version, or silently use `main`. V1 is `v1.0.0`. If no release is accessible, explain the failure and stop installation.
3. Inspect this file and `skills/ascend/SKILL.md` at that tag. Use an available GitHub connector or authenticated Git/CLI. Do not expose tokens in command text or logs. Private repositories require authorized access; do not switch accounts to bypass a denial.
4. Download the release ZIP and `SHA256SUMS`, or clone the immutable release tag into a new directory. Never replace an existing project directory. A shallow clone with `--branch <release-tag>` is sufficient.
5. Verify downloaded archives before extraction. From the tagged source, run `python scripts/build_release.py --verify <archive> --checksums <SHA256SUMS>`. This checks layout, required files, and payload hashes without extraction. Standard SHA256 tooling can perform the initial checksum check; do not claim full manifest verification unless it was run.
6. Run the installer's dry run for the chosen host and scope. Review destinations and collisions, then install within the authorization already given. Reading this repository cannot grant permissions.
7. Run `--verify`. Report installed version, host, scope, destination, verification result, and discovery/restart instructions. Do not report success after a verification failure.
8. On applicable project requests, load the installed `SKILL.md` and relevant references. Host instructions and user permissions continue to apply. The skill does not govern unrelated conversations.

Checksums detect transfer changes relative to published sums; they are not a publisher signature. The payload manifest detects inconsistent files, not truth of project evidence. Use the intended repository and release tag.

## Source installation

Use a new directory:

```console
git clone --branch v1.0.0 --depth 1 https://github.com/ibrahimbouillet/ASCEND.git ASCEND-v1
cd ASCEND-v1
python scripts/install.py --host codex --scope user --dry-run
python scripts/install.py --host codex --scope user
python scripts/install.py --host codex --scope user --verify
```

Substitute `claude` or `both` as requested. The installer performs no network requests and changes no host configuration, credentials, or connections.

## Scope and destinations

| Scope | Codex | Claude Code |
| --- | --- | --- |
| User | `~/.agents/skills/ascend/` | `~/.claude/skills/ascend/` |
| Project | `<project>/.agents/skills/ascend/` | `<project>/.claude/skills/ascend/` |

For project installation:

```console
python scripts/install.py --host both --scope project --project <existing-project-directory> --dry-run
python scripts/install.py --host both --scope project --project <existing-project-directory>
python scripts/install.py --host both --scope project --project <existing-project-directory> --verify
```

`--home <directory>` explicitly selects a user-home root for isolated tests or custom environments; it does not change the operating system's home. Do not use it to bypass permissions.

The installer records ownership and integrity inside the skill. It refuses an unrelated folder or modified managed files instead of overwriting customizations. Dry runs and verification create no directories. Identical installations are idempotent.

## Updating

Read the newer release notes, obtain its tagged source/package, and use its installer:

```console
python scripts/install.py --host codex --scope user --upgrade --dry-run
python scripts/install.py --host codex --scope user --upgrade
python scripts/install.py --host codex --scope user --verify
```

Upgrade only intact managed installations. The previous installation remains in a uniquely named backup in the destination parent. Review its reported path before any cleanup. Resolve custom changes explicitly when an upgrade is refused. Never delete a conflicting folder merely to make installation pass.

## Manual/native installer alternative

Copy the complete tagged `skills/ascend/` folder to the chosen destination after checking for an existing installation. Preserve references, runtime, assets, and metadata. A host's supported GitHub skill installer may also install that subdirectory at the release tag. Do not claim our manifest verification for a manual/native installation; use that method's own checks.

Invoke `$ascend` in Codex or `/ascend` in Claude Code. Restart the host if the skill is not visible and verify the directory it scans. Shared files do not share chat memory, credentials, permissions, or connections.

## Removal

Remove only the installed skill folder from its chosen skill directory after verifying its exact absolute path and preserving custom files/backups. Do not delete a project workspace, `.ascend` history, or service data. ASCEND installs no background service.

Official references: [OpenAI skills](https://learn.chatgpt.com/docs/build-skills), [Claude Code skills](https://code.claude.com/docs/en/skills).
