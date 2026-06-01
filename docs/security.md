# Security

Release Copilot is local and does not run a server.

## Data Flow

- `snapshot` and `draft` read local git metadata and optional check command
  output.
- `apply` runs git and GitHub CLI commands only with `--execute`.
- The plugin does not send data to network services by itself.

## Review Before Publishing

Before tagging or creating a GitHub release:

- Review dirty working tree state.
- Review failed checks.
- Review generated release notes for secrets and private draft text.
- Confirm the tag and release title.
- Confirm `gh` authentication and target repository.

## Check Commands

`--check-command` runs through the local shell because release checks often need
project-specific commands. Use trusted commands only.

