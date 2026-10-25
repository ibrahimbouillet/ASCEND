# Releasing ASCEND

A shipped version is a GitHub Release, not only a commit or local archive. Preserve prior tags and assets; use a new version for corrections.

1. Update root `VERSION`, skill metadata, dashboard version, README release link, and changelog. Retain MIT notices in the repository and installed skill.
2. Run relevant local checks and GitHub CI. State environments and integrations not exercised. Keep source/evidence free of secrets, personal paths, and real project captures.
3. Build and verify in a fresh version-specific directory:

   ```console
   python scripts/build_release.py --output .local/dist-<version>
   python scripts/build_release.py --verify .local/dist-<version>/ascend-<version>.zip --checksums .local/dist-<version>/SHA256SUMS
   ```

4. Extract the verified package into a new location. Exercise its actual installer for both hosts using a temporary home/project: dry run, install, verify, and idempotent repeat. Never use a real user home for these tests.
5. Commit source and validation notes, push, and require CI to pass. Create an annotated `v<version>` tag at that verified commit and push that exact tag.
6. Create release notes describing behavior, installation, checks, and limits. Attach the ZIP, `SHA256SUMS`, and `release-manifest.json`. A draft can hold the assets while checking; publish after checks pass.
7. Download GitHub assets into a fresh directory and verify again. Compare the tag commit to the intended source; confirm published status, stable/prerelease state, and latest version.
8. Report release URL, repository-link installation request, and repository visibility. A private release requires authenticated read access. Packaging tests do not establish business efficacy.

The payload allowlist excludes development tests, evaluation datasets, `.git`, caches, and local `.ascend` records. Checksums and manifests establish consistency, not publisher signatures or truth of project evidence.

CI tests Windows/Linux on Python 3.11/3.14, then builds and verifies a distribution. It does not publish a release or change repository visibility automatically.
