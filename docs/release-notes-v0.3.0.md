# v0.3.0

Install and ecosystem-awareness upgrade.

## Features

- Add `scripts/install_plugin.py` for one-command installation after cloning
  into `~/plugins/release-copilot`.
- Automatically upsert the personal Codex marketplace entry during install.
- Clean up the obsolete repo-local marketplace registration used by prerelease
  installer experiments.
- Add `doctor` command for local prerequisite checks and release tooling
  detection.
- Detect semantic-release, release-please, Changesets, and GoReleaser from
  common config files, package metadata, and GitHub workflows.
- Include detected release tooling in snapshots and drafts.
- Add competitor comparison documentation and clarify Release Copilot's
  human-in-the-loop positioning.

## Validation

- Unit tests cover release tool detection and personal marketplace install
  helpers.
- Source and installed plugin validation pass.
