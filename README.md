# Release Copilot

Codex personal plugin for source-grounded release work.

Release Copilot collects local git context, detects existing release automation,
classifies conventional commits, recommends the next semantic version, runs
explicit verification commands, and drafts PR descriptions, release notes,
changelog entries, tag plans, and GitHub release plans. It defaults to read-only
drafting. Tags and GitHub releases require `apply --execute`.

## Install

```bash
mkdir -p ~/plugins
git clone https://github.com/Meapri/release-copilot.git ~/plugins/release-copilot
python3 ~/plugins/release-copilot/scripts/install_plugin.py
```

The installer updates your personal Codex marketplace and installs the plugin.
Then start a new Codex thread so the skill is loaded.

## Included

- `skills/release-copilot/SKILL.md`: Codex routing and safety workflow
- `scripts/release_copilot.py`: local release snapshot, draft, and apply helper
- `scripts/install_plugin.py`: one-command personal marketplace installer
- `tests/test_release_copilot.py`: unit tests for release collection and plans

No MCP server is included.

## Usage

Draft a release bundle from the current repository:

```bash
python3 scripts/release_copilot.py draft --repo .
```

Include checks:

```bash
python3 scripts/release_copilot.py draft \
  --repo . \
  --check-command "git diff --check" \
  --check-command "python3 -m unittest discover -s tests -v"
```

Get structured JSON:

```bash
python3 scripts/release_copilot.py snapshot --repo . --format json
```

Check local prerequisites and detect release tooling:

```bash
python3 scripts/release_copilot.py doctor --repo .
```

Write release artifact files:

```bash
python3 scripts/release_copilot.py artifacts \
  --repo . \
  --version 1.2.3 \
  --tag v1.2.3 \
  --output-dir release-artifacts
```

Render a changelog entry:

```bash
python3 scripts/release_copilot.py changelog --repo . --version 1.2.3 --tag v1.2.3
```

Update `CHANGELOG.md` only when requested:

```bash
python3 scripts/release_copilot.py changelog --repo . --version 1.2.3 --tag v1.2.3 --write
```

Dry-run tag and GitHub release commands:

```bash
python3 scripts/release_copilot.py apply \
  --repo . \
  --tag v1.2.3 \
  --github-release \
  --notes-file RELEASE_NOTES.md
```

Execute only after reviewing the dry run:

```bash
python3 scripts/release_copilot.py apply \
  --repo . \
  --tag v1.2.3 \
  --github-release \
  --notes-file RELEASE_NOTES.md \
  --execute
```

## Safety

- Draft and snapshot commands are read-only except optional `--output`.
- `apply` prints commands by default and runs them only with `--execute`.
- `apply --github-release` requires `--tag`.
- `apply --execute` refuses a dirty working tree unless `--allow-dirty` is set.
- Check commands are explicit user/Codex-selected commands, not automatic hidden
  execution.
- Drafts include dirty working tree state and failed checks instead of hiding
  them.

## Similar Tools

Release Copilot is not trying to replace CI-first release systems such as
semantic-release, release-please, Changesets, or GoReleaser. It detects those
tools and works best as a Codex-local release reviewer, drafter, and dry-run
planner. See [Comparison](docs/comparison.md).
