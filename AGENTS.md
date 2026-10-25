# Working on ASCEND

For installation requests, follow [INSTALL.md](INSTALL.md). These maintenance instructions do not authorize changing an installation target or unrelated project.

- Keep source, documentation, release notes, and UI text in English. Retain raw evaluation outputs as produced.
- Keep the skill portable between Codex and Claude Code. Connector access, installation integrity, host execution, and project efficacy are separate claims.
- Preserve existing work, histories, and customized installations. Exclude credentials, private machine paths, real customer data, and local captures from source and releases.
- Run `python -m unittest discover -s tests -v` for runtime, context, installer, or distribution changes. Run relevant browser checks for dashboard behavior. Retain demonstrated failures and regression checks.
- Every shipped version must be a GitHub Release with a matching immutable Git tag, release notes, verified ZIP, payload manifest, and SHA256 sums. A version bump or push alone does not ship a release.
- Keep `VERSION`, skill metadata, dashboard version, README, and changelog consistent. Never replace a shipped tag or asset; publish a new version.
- Build in a fresh version-specific directory, verify the archive, and test installation from an extracted package for both hosts in isolated locations. Record material validation limits.
- A release request does not authorize changing private repository visibility. Use the user's explicitly authorized visibility.

See [docs/RELEASING.md](docs/RELEASING.md).
