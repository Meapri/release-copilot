# Release Copilot

Codex personal plugin for source-grounded release work.

Release Copilot collects local git context, runs explicit verification commands,
and drafts PR descriptions, release notes, changelog entries, tag plans, and
GitHub release plans. It defaults to read-only drafting. Tags and GitHub releases
require `apply --execute`.

## Included

- `skills/release-copilot/SKILL.md`: Codex routing and safety workflow
- `scripts/release_copilot.py`: local release snapshot, draft, and apply helper
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
- Check commands are explicit user/Codex-selected commands, not automatic hidden
  execution.
- Drafts include dirty working tree state and failed checks instead of hiding
  them.

