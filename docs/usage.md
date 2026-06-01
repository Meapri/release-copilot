# Usage

## Draft

Use `draft` for the normal Codex workflow:

```bash
python3 scripts/release_copilot.py draft --repo .
```

Options:

- `--base`: compare base ref. Defaults to upstream merge-base or latest tag.
- `--head`: compare head ref. Defaults to `HEAD`.
- `--version`: explicit release version.
- `--tag`: explicit tag name.
- `--title`: release title.
- `--check-command`: command to run and include in the verification section.
- `--output`: write the draft to a file.
- `--artifact-dir`: also write PR, release note, changelog, and snapshot files.

The draft includes conventional-commit categories, a recommended semver bump,
the recommended next version when a current version is detected, and a GitHub
compare URL when the repository has a GitHub `origin` remote.

## Snapshot

Use `snapshot` when another tool or Codex needs structured context:

```bash
python3 scripts/release_copilot.py snapshot --repo . --format json
```

`--format markdown` returns the same draft-style markdown as `draft`.

## Artifacts

Use `artifacts` to write release files:

```bash
python3 scripts/release_copilot.py artifacts --repo . --version 1.2.3 --tag v1.2.3 --output-dir release-artifacts
```

It writes:

- `PR_DESCRIPTION.md`
- `RELEASE_NOTES.md`
- `CHANGELOG_ENTRY.md`
- `RELEASE_DRAFT.md`
- `RELEASE_SNAPSHOT.json`

## Changelog

Render a changelog entry:

```bash
python3 scripts/release_copilot.py changelog --repo . --version 1.2.3 --tag v1.2.3
```

Update a changelog file only when requested:

```bash
python3 scripts/release_copilot.py changelog --repo . --version 1.2.3 --tag v1.2.3 --file CHANGELOG.md --write
```

## Apply

`apply` is safe by default and only prints planned commands:

```bash
python3 scripts/release_copilot.py apply --repo . --tag v1.2.3 --github-release --notes-file RELEASE_NOTES.md
```

Add `--execute` only after the user explicitly asks to create the tag or release:

```bash
python3 scripts/release_copilot.py apply --repo . --tag v1.2.3 --github-release --notes-file RELEASE_NOTES.md --execute
```

`--github-release` requires `--tag`. `--execute` refuses a dirty working tree
unless `--allow-dirty` is passed.

## Gemini Writing Copilot

Release Copilot drafts are source-grounded and intentionally plain. If Gemini
Writing Copilot is installed, Codex can pass the PR description or release notes
section to it for final prose polish, then review the output for factual
accuracy.
