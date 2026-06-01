---
name: release-copilot
description: "Use when the user asks Codex to prepare a release, PR description, changelog, release notes, tag, GitHub release, version summary, or release checklist from a local git repository. Use for source-grounded release writing and verification summaries. Do not use for general coding, debugging, or architecture decisions unless the requested deliverable is a release artifact."
---

# Release Copilot

Use this skill when the requested deliverable is a release artifact or release workflow.

## When To Use

Use Release Copilot for:

- PR descriptions and reviewer notes from local git changes
- Release notes and changelog entries
- Version and tag planning
- Conventional commit classification
- Recommended semantic version bumps
- GitHub compare URLs
- Release readiness snapshots
- Test or validation summaries for release artifacts
- Writing PR/release/changelog artifact files
- Updating changelog entries
- Dry-run GitHub release plans
- Executing tags or GitHub releases only after explicit user approval

Do not use it for:

- Implementing code changes
- Debugging root causes
- Refactoring decisions
- Security review beyond release-artifact hygiene checks

## Script

Resolve paths relative to this skill directory:

- Release script: `../../scripts/release_copilot.py`

## Default Workflow

Start read-only. Collect context and draft artifacts:

```bash
python3 /Users/naen/plugins/release-copilot/scripts/release_copilot.py draft \
  --repo . \
  --check-command "git diff --check"
```

Add project-specific checks when obvious:

- Python: `python3 -m pytest` or the repo's documented test command
- Node: `npm test`, `npm run lint`, or the package scripts the repo uses
- Plugin work: plugin validation and skill validation commands

Use `snapshot` when Codex needs structured data:

```bash
python3 /Users/naen/plugins/release-copilot/scripts/release_copilot.py snapshot --repo . --format json
```

Use `artifacts` when the user wants files:

```bash
python3 /Users/naen/plugins/release-copilot/scripts/release_copilot.py artifacts \
  --repo . \
  --version 1.2.3 \
  --tag v1.2.3 \
  --output-dir release-artifacts
```

Use `changelog` for changelog entries. Print first, write only when asked:

```bash
python3 /Users/naen/plugins/release-copilot/scripts/release_copilot.py changelog \
  --repo . \
  --version 1.2.3 \
  --tag v1.2.3
```

## Writing Polish

The script returns source-grounded drafts. If Gemini Writing Copilot is available and the user asks for polished prose, Codex may pass the PR/release-note draft to Gemini Writing Copilot, then review the final result for factual accuracy before replying.

Keep engineering claims grounded in the local snapshot. Remove invented features, tests, dates, issue IDs, compatibility promises, or performance claims.

## Safe Apply

Never create a git tag, push a tag, or create a GitHub release unless the user explicitly asks for that action.

Dry-run apply commands first:

```bash
python3 /Users/naen/plugins/release-copilot/scripts/release_copilot.py apply \
  --repo . \
  --tag v1.2.3 \
  --github-release \
  --notes-file RELEASE_NOTES.md
```

Only execute after explicit approval:

```bash
python3 /Users/naen/plugins/release-copilot/scripts/release_copilot.py apply \
  --repo . \
  --tag v1.2.3 \
  --github-release \
  --notes-file RELEASE_NOTES.md \
  --execute
```

Before execution, check:

- The working tree state is intentional.
- Required tests/checks are present and passing, or failures are disclosed.
- The tag name and release title are correct.
- Release notes contain no secrets or private draft text.
- `gh` is authenticated if creating a GitHub release.

`apply --github-release` requires `--tag`. `apply --execute` refuses a dirty working tree unless `--allow-dirty` is passed.

## Response Handling

When returning release artifacts, lead with the final artifact the user asked for. Keep command output summaries concise. Mention failed checks clearly and do not hide dirty working tree state.
