# Security

Release Copilot is local and does not run a server.

## Data Flow

- `snapshot` and `draft` read local git metadata and optional check command
  output.
- `doctor` reads local tool availability and release automation configuration.
- `artifacts` writes release drafts to the selected output directory.
- `changelog --write` modifies the selected changelog file.
- `apply` runs git and GitHub CLI commands only with `--execute`.
- The plugin does not send data to network services by itself.

## Review Before Publishing

Before tagging or creating a GitHub release:

- Review dirty working tree state.
- Review failed checks.
- Review generated release notes for secrets and private draft text.
- Confirm the tag and release title.
- Confirm `gh` authentication and target repository.
- If release-please, semantic-release, Changesets, or GoReleaser are detected,
  verify whether Release Copilot should only draft/review instead of publishing.

`apply --execute` refuses a dirty working tree unless `--allow-dirty` is set.
Prefer a clean tree for release tags.

## Check Commands

`--check-command` runs through the local shell because release checks often need
project-specific commands. Use trusted commands only.
