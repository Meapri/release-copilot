# v0.2.0

Release manager upgrade.

## Features

- Classify conventional commits into release-note sections.
- Recommend semver bump and next version from detected version files or latest
  tag.
- Add GitHub compare URL detection for GitHub `origin` remotes.
- Add `artifacts` command to write PR description, release notes, changelog
  entry, full draft, and JSON snapshot files.
- Add `changelog` command with safe print-by-default behavior and explicit
  `--write` for file updates.
- Make GitHub release apply plans require a tag.
- Make `apply --execute` refuse dirty working trees unless `--allow-dirty` is
  set.

## Validation

- Unit tests cover version recommendation, commit categorization, artifact
  writing, changelog insertion, dry-run plans, and CLI output.

