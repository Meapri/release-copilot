# Comparison

Release Copilot is intentionally different from CI-first release automation
tools. It is a Codex-local assistant for preparing release artifacts, checking
local state, and keeping a human in the loop before tags or GitHub releases are
created.

## Similar Tools

### semantic-release

semantic-release is a CI/CD automation tool for fully automated version
management, release notes, and package publishing. It is strongest when a
project wants releases to happen automatically after CI succeeds on a release
branch.

Release Copilot is more conservative: it drafts and plans locally, then requires
explicit execution for tags and releases.

### release-please

release-please parses git history, looks for Conventional Commits, and maintains
release PRs that update changelogs, versions, and GitHub releases. It is a good
fit when a team wants the release process represented as a pull request.

Release Copilot complements that model by generating local release snapshots,
review text, and artifact files inside Codex without requiring a release PR
workflow.

### Changesets

Changesets is focused on package versioning and changelogs, especially for
multi-package repositories. Contributors write changeset files that describe the
intended semver bump and summary, then Changesets automates versioning,
dependency updates, changelogs, and publishing.

Release Copilot does not replace that intent-file workflow. It can detect
Changesets and should act as a reviewer/drafter rather than a publisher when a
repo already uses it.

### GoReleaser

GoReleaser is a release engineering tool that can generate changelogs from git,
GitHub, GitLab, Gitea, or GitHub-native release notes, and it is especially
strong for building and publishing compiled artifacts.

Release Copilot is lighter-weight and language-agnostic. It does not build
binaries or package artifacts; it prepares release context, notes, and safe
commands for Codex-led workflows.

## Positioning

Use Release Copilot when:

- You want Codex to inspect local repo state before release writing.
- You want release notes, PR descriptions, changelog entries, and snapshots in
  one local workflow.
- You want a dry-run-first safety model.
- You want Gemini Writing Copilot or Codex to polish prose after factual
  context is collected.
- You do not want CI to publish automatically without human review.

Use a competitor instead when:

- You need full CI/CD package publishing automation.
- You need monorepo package version orchestration.
- You need binary build matrices, package manager publishing, or artifact
  signing.

## References

- semantic-release: https://www.semantic-release.org/
- release-please: https://github.com/googleapis/release-please
- Changesets: https://github.com/changesets/changesets
- GoReleaser changelog docs: https://www.goreleaser.com/customization/publish/changelog/

