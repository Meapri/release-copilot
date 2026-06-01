#!/usr/bin/env python3
"""Collect release context and draft release artifacts from a local git repo."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time


VERSION_FILE_PATTERNS = (
    ("package.json", re.compile(r'"version"\s*:\s*"([^"]+)"')),
    ("pyproject.toml", re.compile(r'(?m)^version\s*=\s*"([^"]+)"')),
    ("Cargo.toml", re.compile(r'(?m)^version\s*=\s*"([^"]+)"')),
    (".codex-plugin/plugin.json", re.compile(r'"version"\s*:\s*"([^"]+)"')),
    ("VERSION", re.compile(r"^\s*([^\s]+)\s*$")),
)

CHANGE_CATEGORY_TITLES = {
    "breaking": "Breaking",
    "features": "Added",
    "fixes": "Fixed",
    "performance": "Performance",
    "docs": "Documentation",
    "tests": "Tests",
    "chores": "Chores",
    "other": "Other",
}

CONVENTIONAL_RE = re.compile(r"^(?P<type>[A-Za-z]+)(?:\([^)]+\))?(?P<breaking>!)?:\s*(?P<body>.+)$")
SEMVER_RE = re.compile(r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)")


@dataclass
class CommandResult:
    command: str
    exit_code: int
    duration_sec: float
    stdout_tail: str
    stderr_tail: str


@dataclass
class VersionInfo:
    path: str
    version: str


@dataclass
class ReleaseSnapshot:
    repo_root: str
    branch: str
    head: str
    base_ref: str
    latest_tag: str
    compare_range: str
    remote_url: str
    compare_url: str
    release_tools: list[str]
    status_short: str
    changed_files: str
    diff_stat: str
    commits: str
    change_categories: dict[str, list[str]]
    recommended_bump: str
    recommended_version: str
    versions: list[VersionInfo]
    checks: list[CommandResult]


def run(
    command: list[str],
    *,
    cwd: Path,
    check: bool = False,
    timeout_sec: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        check=check,
        text=True,
        capture_output=True,
        timeout=timeout_sec,
    )


def git_output(repo: Path, args: list[str], *, timeout_sec: int = 30) -> str:
    proc = run(["git", *args], cwd=repo, timeout_sec=timeout_sec)
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def repo_root(path: Path) -> Path:
    proc = run(["git", "rev-parse", "--show-toplevel"], cwd=path)
    if proc.returncode != 0:
        raise SystemExit(f"Not a git repository: {path}")
    return Path(proc.stdout.strip()).resolve()


def latest_tag(repo: Path) -> str:
    return git_output(repo, ["describe", "--tags", "--abbrev=0"])


def current_remote_url(repo: Path) -> str:
    remote = git_output(repo, ["remote", "get-url", "origin"])
    return normalize_remote_url(remote)


def normalize_remote_url(remote: str) -> str:
    remote = remote.strip()
    if not remote:
        return ""
    if remote.startswith("git@github.com:"):
        path = remote.removeprefix("git@github.com:")
        return "https://github.com/" + path.removesuffix(".git")
    if remote.startswith("https://github.com/"):
        return remote.removesuffix(".git")
    if remote.startswith("http://github.com/"):
        return "https://" + remote.removeprefix("http://").removesuffix(".git")
    return remote


def compare_url(remote_url: str, base_ref: str, head_ref: str) -> str:
    if not remote_url.startswith("https://github.com/") or not base_ref:
        return ""
    return f"{remote_url}/compare/{base_ref}...{head_ref}"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _package_json_tool_names(repo: Path) -> set[str]:
    path = repo / "package.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    names: set[str] = set()
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        values = data.get(section, {})
        if isinstance(values, dict):
            names.update(values)
    scripts = data.get("scripts", {})
    if isinstance(scripts, dict):
        names.update(str(value) for value in scripts.values())
    return names


def _workflow_contains(repo: Path, needle: str) -> bool:
    workflows = repo / ".github" / "workflows"
    if not workflows.is_dir():
        return False
    for path in workflows.glob("*"):
        if path.suffix.lower() not in {".yml", ".yaml"}:
            continue
        if needle.lower() in _read_text(path).lower():
            return True
    return False


def detect_release_tools(repo: Path) -> list[str]:
    tools: list[str] = []
    package_names = _package_json_tool_names(repo)

    semantic_release_files = (
        ".releaserc",
        ".releaserc.json",
        ".releaserc.yml",
        ".releaserc.yaml",
        "release.config.js",
        "release.config.cjs",
        "release.config.mjs",
    )
    if any((repo / name).exists() for name in semantic_release_files) or any(
        "semantic-release" in name for name in package_names
    ):
        tools.append("semantic-release")

    if (
        (repo / "release-please-config.json").exists()
        or (repo / ".release-please-manifest.json").exists()
        or _workflow_contains(repo, "release-please")
    ):
        tools.append("release-please")

    if (repo / ".changeset").is_dir() or any(name.startswith("@changesets/") for name in package_names):
        tools.append("changesets")

    goreleaser_files = (".goreleaser.yml", ".goreleaser.yaml", "goreleaser.yml", "goreleaser.yaml")
    if any((repo / name).exists() for name in goreleaser_files) or _workflow_contains(repo, "goreleaser"):
        tools.append("goreleaser")

    return tools


def default_base(repo: Path) -> str:
    upstream = git_output(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
    if upstream:
        merge_base = git_output(repo, ["merge-base", "HEAD", upstream])
        if merge_base:
            return merge_base
    tag = latest_tag(repo)
    return tag


def compare_args(base_ref: str, head_ref: str) -> list[str]:
    if base_ref:
        return [f"{base_ref}..{head_ref}"]
    return []


def strip_commit_hash(commit: str) -> str:
    return re.sub(r"^[0-9a-f]{6,40}\s+", "", commit.strip())


def categorize_commit(message: str) -> tuple[str, str, bool]:
    message = strip_commit_hash(message)
    match = CONVENTIONAL_RE.match(message)
    if not match:
        breaking = "BREAKING CHANGE" in message or "breaking:" in message.lower()
        return ("breaking" if breaking else "other", message, breaking)

    commit_type = match.group("type").lower()
    body = match.group("body").strip()
    breaking = bool(match.group("breaking")) or "BREAKING CHANGE" in message
    if breaking:
        return "breaking", body, True
    if commit_type == "feat":
        return "features", body, False
    if commit_type in {"fix", "bugfix", "hotfix"}:
        return "fixes", body, False
    if commit_type in {"perf", "speed"}:
        return "performance", body, False
    if commit_type == "docs":
        return "docs", body, False
    if commit_type in {"test", "tests"}:
        return "tests", body, False
    if commit_type in {"chore", "build", "ci", "refactor", "style"}:
        return "chores", body, False
    return "other", body, False


def categorize_commits(commits: str) -> dict[str, list[str]]:
    categories = {key: [] for key in CHANGE_CATEGORY_TITLES}
    for line in commits.splitlines():
        if not line.strip():
            continue
        category, body, _breaking = categorize_commit(line)
        categories.setdefault(category, []).append(body)
    return {key: value for key, value in categories.items() if value}


def categorize_changed_files(changed_files: str) -> dict[str, list[str]]:
    items: list[str] = []
    for line in changed_files.splitlines():
        if line.strip():
            items.append(line.strip())
    return {"other": items[:20]} if items else {}


def recommended_bump_from_categories(categories: dict[str, list[str]]) -> str:
    if categories.get("breaking"):
        return "major"
    if categories.get("features"):
        return "minor"
    if any(categories.get(key) for key in ("fixes", "performance", "docs", "tests", "chores", "other")):
        return "patch"
    return "none"


def parse_semver(version: str) -> tuple[int, int, int] | None:
    match = SEMVER_RE.match(version.strip())
    if not match:
        return None
    return int(match.group("major")), int(match.group("minor")), int(match.group("patch"))


def bump_version(version: str, bump: str) -> str:
    parsed = parse_semver(version)
    if not parsed or bump == "none":
        return ""
    major, minor, patch = parsed
    prefix = "v" if version.strip().startswith("v") else ""
    if bump == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump == "minor":
        minor += 1
        patch = 0
    elif bump == "patch":
        patch += 1
    else:
        return ""
    return f"{prefix}{major}.{minor}.{patch}"


def detected_primary_version(versions: list[VersionInfo], latest: str) -> str:
    if versions:
        return versions[0].version
    return latest


def version_infos(repo: Path) -> list[VersionInfo]:
    found: list[VersionInfo] = []
    for relative, pattern in VERSION_FILE_PATTERNS:
        path = repo / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        match = pattern.search(text)
        if match:
            found.append(VersionInfo(path=relative, version=match.group(1).strip()))
    return found


def tail(text: str, max_chars: int = 4000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:].lstrip()


def run_check(repo: Path, command: str, *, timeout_sec: int) -> CommandResult:
    started = time.monotonic()
    proc = subprocess.run(
        command,
        cwd=str(repo),
        shell=True,
        text=True,
        capture_output=True,
        timeout=timeout_sec,
    )
    duration = time.monotonic() - started
    return CommandResult(
        command=command,
        exit_code=proc.returncode,
        duration_sec=round(duration, 3),
        stdout_tail=tail(proc.stdout),
        stderr_tail=tail(proc.stderr),
    )


def collect_snapshot(
    *,
    repo: Path,
    base_ref: str = "",
    head_ref: str = "HEAD",
    checks: list[str] | None = None,
    check_timeout_sec: int = 600,
) -> ReleaseSnapshot:
    repo = repo_root(repo)
    base = base_ref or default_base(repo)
    diff_range = compare_args(base, head_ref)
    log_range = diff_range or ["--max-count=20"]
    check_results = [run_check(repo, command, timeout_sec=check_timeout_sec) for command in checks or []]
    commits = git_output(repo, ["log", "--oneline", *log_range])
    status_short = git_output(repo, ["status", "--short"])
    changed_files = git_output(repo, ["diff", "--name-status", *diff_range])
    diff_stat = git_output(repo, ["diff", "--stat", *diff_range])
    if status_short and not changed_files:
        changed_files = status_short
        diff_stat = git_output(repo, ["diff", "--stat"]) or "[working tree has untracked or staged changes]"
    categories = categorize_commits(commits) or categorize_changed_files(changed_files)
    bump = recommended_bump_from_categories(categories)
    latest = latest_tag(repo)
    versions = version_infos(repo)
    primary_version = detected_primary_version(versions, latest)
    remote = current_remote_url(repo)
    return ReleaseSnapshot(
        repo_root=str(repo),
        branch=git_output(repo, ["branch", "--show-current"]),
        head=git_output(repo, ["rev-parse", "--short", head_ref]),
        base_ref=base,
        latest_tag=latest,
        compare_range=diff_range[0] if diff_range else "working tree",
        remote_url=remote,
        compare_url=compare_url(remote, base, head_ref),
        release_tools=detect_release_tools(repo),
        status_short=status_short,
        changed_files=changed_files,
        diff_stat=diff_stat,
        commits=commits,
        change_categories=categories,
        recommended_bump=bump,
        recommended_version=bump_version(primary_version, bump),
        versions=versions,
        checks=check_results,
    )


def parse_change_lines(snapshot: ReleaseSnapshot) -> list[str]:
    lines: list[str] = []
    for commit in snapshot.commits.splitlines():
        text = strip_commit_hash(commit)
        if not text:
            continue
        lines.append(text)
    if lines:
        return lines[:12]
    for changed in snapshot.changed_files.splitlines():
        parts = changed.split(maxsplit=1)
        if len(parts) == 2:
            lines.append(f"{parts[0]} {parts[1]}")
    return lines[:12]


def check_summary(checks: list[CommandResult]) -> str:
    if not checks:
        return "- [ ] Add verification commands or note manual testing."
    lines = []
    for result in checks:
        mark = "x" if result.exit_code == 0 else " "
        status = "passed" if result.exit_code == 0 else f"failed with exit code {result.exit_code}"
        lines.append(f"- [{mark}] `{result.command}` {status}")
    return "\n".join(lines)


def version_summary(snapshot: ReleaseSnapshot, explicit_version: str = "") -> str:
    if explicit_version:
        return explicit_version
    if snapshot.versions:
        return ", ".join(f"{item.path}: {item.version}" for item in snapshot.versions)
    return "[version not detected]"


def markdown_list(items: list[str], fallback: str) -> str:
    if not items:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in items)


def render_category_sections(categories: dict[str, list[str]], *, fallback: str) -> str:
    if not categories:
        return markdown_list([], fallback)
    sections: list[str] = []
    for key, title in CHANGE_CATEGORY_TITLES.items():
        items = categories.get(key)
        if not items:
            continue
        sections.append(f"### {title}\n{markdown_list(items, fallback)}")
    return "\n\n".join(sections)


def render_draft(snapshot: ReleaseSnapshot, *, title: str = "", version: str = "", tag: str = "") -> str:
    change_lines = parse_change_lines(snapshot)
    selected_version = version or snapshot.recommended_version
    release_title = title or f"Release {selected_version or tag or snapshot.head}"
    version_text = version_summary(snapshot, version)
    tag_text = tag or (f"v{selected_version}" if selected_version and not selected_version.startswith("v") else selected_version) or "[tag not selected]"
    category_sections = render_category_sections(snapshot.change_categories, fallback="Describe notable changes.")

    sections = [
        "# Release Copilot Draft",
        "## Snapshot",
        f"- Repository: `{snapshot.repo_root}`",
        f"- Branch: `{snapshot.branch or '[detached]'}`",
        f"- Head: `{snapshot.head}`",
        f"- Base: `{snapshot.base_ref or '[not detected]'}`",
        f"- Compare range: `{snapshot.compare_range}`",
        f"- Compare URL: {snapshot.compare_url or '[not available]'}",
        f"- Detected release tools: {', '.join(snapshot.release_tools) if snapshot.release_tools else '[none]'}",
        f"- Latest tag: `{snapshot.latest_tag or '[none]'}`",
        f"- Version: `{version_text}`",
        f"- Recommended bump: `{snapshot.recommended_bump}`",
        f"- Recommended next version: `{snapshot.recommended_version or '[not detected]'}`",
        "",
        "## Working Tree",
        "```text",
        snapshot.status_short or "clean",
        "```",
        "",
        "## Changed Files",
        "```text",
        snapshot.changed_files or "[no changed files in compare range]",
        "```",
        "",
        "## Diff Stat",
        "```text",
        snapshot.diff_stat or "[no diff stat]",
        "```",
        "",
        "## Verification",
        check_summary(snapshot.checks),
        "",
        "## PR Description Draft",
        f"### Summary\n{markdown_list(change_lines[:5], 'Summarize the main change.')}",
        "",
        "### Changes",
        category_sections,
        "",
        "### Validation",
        check_summary(snapshot.checks),
        "",
        "### Reviewer Notes",
        "- [ ] Confirm version, migration, and compatibility notes.",
        "- [ ] Confirm no secrets or private data are included in release artifacts.",
        "",
        "## Release Notes Draft",
        f"### {release_title}",
        category_sections,
        "",
        "### Compatibility",
        "- [ ] Add breaking changes, migration notes, or mark as none.",
        "",
        "## Changelog Entry Draft",
        f"## {tag_text} - [date]",
        category_sections,
        "",
        "## Suggested Dry-Run Commands",
        f"- Tag: `python3 scripts/release_copilot.py apply --tag {shlex.quote(tag_text)} --dry-run`",
        f"- GitHub release: `python3 scripts/release_copilot.py apply --tag {shlex.quote(tag_text)} --github-release --notes-file RELEASE_NOTES.md --dry-run`",
    ]
    return "\n".join(sections).strip() + "\n"


def section_between(markdown: str, start: str, end: str) -> str:
    start_index = markdown.find(start)
    if start_index == -1:
        return ""
    start_index += len(start)
    end_index = markdown.find(end, start_index)
    if end_index == -1:
        end_index = len(markdown)
    return markdown[start_index:end_index].strip() + "\n"


def artifacts_from_draft(draft: str) -> dict[str, str]:
    return {
        "PR_DESCRIPTION.md": section_between(draft, "## PR Description Draft", "## Release Notes Draft"),
        "RELEASE_NOTES.md": section_between(draft, "## Release Notes Draft", "## Changelog Entry Draft"),
        "CHANGELOG_ENTRY.md": section_between(draft, "## Changelog Entry Draft", "## Suggested Dry-Run Commands"),
        "RELEASE_DRAFT.md": draft,
    }


def write_artifacts(
    snapshot: ReleaseSnapshot,
    *,
    output_dir: Path,
    title: str = "",
    version: str = "",
    tag: str = "",
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    draft = render_draft(snapshot, title=title, version=version, tag=tag)
    artifacts = artifacts_from_draft(draft)
    artifacts["RELEASE_SNAPSHOT.json"] = snapshot_to_json(snapshot) + "\n"
    written: list[Path] = []
    for filename, content in artifacts.items():
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def render_changelog_entry(snapshot: ReleaseSnapshot, *, version: str = "", tag: str = "", entry_date: str = "") -> str:
    selected_version = version or snapshot.recommended_version or tag or snapshot.head
    selected_date = entry_date or date.today().isoformat()
    heading = tag or (f"v{selected_version}" if selected_version and not selected_version.startswith("v") else selected_version)
    return (
        f"## {heading} - {selected_date}\n\n"
        + render_category_sections(snapshot.change_categories, fallback="Describe notable changes.")
        + "\n"
    )


def update_changelog_text(existing: str, entry: str) -> str:
    if not existing.strip():
        return "# Changelog\n\n" + entry.strip() + "\n"
    lines = existing.splitlines()
    insert_at = 0
    if lines and lines[0].lstrip().startswith("# "):
        insert_at = 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
    before = "\n".join(lines[:insert_at]).rstrip()
    after = "\n".join(lines[insert_at:]).lstrip()
    parts = [part for part in (before, entry.strip(), after) if part]
    return "\n\n".join(parts) + "\n"


def snapshot_to_json(snapshot: ReleaseSnapshot) -> str:
    return json.dumps(asdict(snapshot), ensure_ascii=False, indent=2)


def write_output(text: str, output: str) -> None:
    if output:
        Path(output).expanduser().write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def planned_apply_commands(args: argparse.Namespace) -> list[list[str]]:
    commands: list[list[str]] = []
    if args.github_release and not args.tag:
        raise SystemExit("--tag is required when --github-release is selected.")
    if args.tag:
        message = args.message or f"Release {args.tag}"
        commands.append(["git", "tag", "-a", args.tag, "-m", message])
        if args.push_tag:
            commands.append(["git", "push", "origin", args.tag])
    if args.github_release:
        command = ["gh", "release", "create", args.tag or args.title]
        if args.title:
            command.extend(["--title", args.title])
        if args.notes_file:
            command.extend(["--notes-file", args.notes_file])
        elif args.notes:
            command.extend(["--notes", args.notes])
        else:
            command.extend(["--notes", "Release notes pending."])
        commands.append(command)
    return commands


def render_commands(commands: list[list[str]]) -> str:
    if not commands:
        return "No apply commands selected.\n"
    return "\n".join(" ".join(shlex.quote(part) for part in command) for command in commands) + "\n"


def run_apply(args: argparse.Namespace) -> int:
    repo = repo_root(Path(args.repo).expanduser())
    commands = planned_apply_commands(args)
    if args.dry_run or not args.execute:
        print(render_commands(commands), end="")
        return 0
    if not args.allow_dirty and git_output(repo, ["status", "--short"]):
        raise SystemExit("Working tree is dirty. Commit/stash changes or pass --allow-dirty.")
    for command in commands:
        print("$ " + " ".join(shlex.quote(part) for part in command), file=sys.stderr)
        proc = subprocess.run(command, cwd=str(repo), check=False)
        if proc.returncode != 0:
            return proc.returncode
    return 0


def run_doctor(args: argparse.Namespace) -> int:
    failures = 0
    repo = Path(args.repo).expanduser()
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info < (3, 9):
        print("Python check: requires 3.9+")
        failures += 1
    else:
        print("Python check: ok")
    print(f"git: {shutil.which('git') or 'not found'}")
    if not shutil.which("git"):
        failures += 1
    print(f"gh: {shutil.which('gh') or 'not found'}")
    print(f"codex: {shutil.which('codex') or 'not found'}")
    try:
        root = repo_root(repo)
        print(f"Repo: {root}")
        print(f"Branch: {git_output(root, ['branch', '--show-current']) or '[detached]'}")
        tools = detect_release_tools(root)
        print(f"Detected release tools: {', '.join(tools) if tools else '[none]'}")
        if git_output(root, ["status", "--short"]):
            print("Working tree: dirty")
        else:
            print("Working tree: clean")
    except SystemExit as exc:
        print(str(exc))
        failures += 1
    return 0 if failures == 0 else 1


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".", help="Git repository path.")
    parser.add_argument("--base", default="", help="Base ref. Defaults to upstream merge-base or latest tag.")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--check-command", action="append", default=[], help="Command to run and include in output.")
    parser.add_argument("--check-timeout-sec", type=int, default=600)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Release Copilot")
    subcommands = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subcommands.add_parser("snapshot", help="Collect release context.")
    add_common_args(snapshot_parser)
    snapshot_parser.add_argument("--format", choices=("json", "markdown"), default="json")
    snapshot_parser.add_argument("--output", default="")

    draft_parser = subcommands.add_parser("draft", help="Draft release artifacts.")
    add_common_args(draft_parser)
    draft_parser.add_argument("--title", default="")
    draft_parser.add_argument("--version", default="")
    draft_parser.add_argument("--tag", default="")
    draft_parser.add_argument("--output", default="")
    draft_parser.add_argument("--artifact-dir", default="")

    artifacts_parser = subcommands.add_parser("artifacts", help="Write release artifact files.")
    add_common_args(artifacts_parser)
    artifacts_parser.add_argument("--title", default="")
    artifacts_parser.add_argument("--version", default="")
    artifacts_parser.add_argument("--tag", default="")
    artifacts_parser.add_argument("--output-dir", default="release-artifacts")

    changelog_parser = subcommands.add_parser("changelog", help="Render or update a changelog entry.")
    add_common_args(changelog_parser)
    changelog_parser.add_argument("--version", default="")
    changelog_parser.add_argument("--tag", default="")
    changelog_parser.add_argument("--date", default="")
    changelog_parser.add_argument("--file", default="CHANGELOG.md")
    changelog_parser.add_argument("--write", action="store_true")

    doctor_parser = subcommands.add_parser("doctor", help="Check local release-copilot prerequisites.")
    doctor_parser.add_argument("--repo", default=".")

    apply_parser = subcommands.add_parser("apply", help="Plan or execute tag and GitHub release commands.")
    apply_parser.add_argument("--repo", default=".")
    apply_parser.add_argument("--tag", default="")
    apply_parser.add_argument("--title", default="")
    apply_parser.add_argument("--message", default="")
    apply_parser.add_argument("--push-tag", action="store_true")
    apply_parser.add_argument("--github-release", action="store_true")
    apply_parser.add_argument("--notes-file", default="")
    apply_parser.add_argument("--notes", default="")
    apply_parser.add_argument("--execute", action="store_true")
    apply_parser.add_argument("--dry-run", action="store_true")
    apply_parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "doctor":
        return run_doctor(args)
    if args.command in {"snapshot", "draft", "artifacts", "changelog"}:
        snapshot = collect_snapshot(
            repo=Path(args.repo).expanduser(),
            base_ref=args.base,
            head_ref=args.head,
            checks=args.check_command,
            check_timeout_sec=args.check_timeout_sec,
        )
        if args.command == "snapshot":
            output = snapshot_to_json(snapshot) + "\n" if args.format == "json" else render_draft(snapshot)
            write_output(output, args.output)
            return 0
        if args.command == "draft":
            draft = render_draft(snapshot, title=args.title, version=args.version, tag=args.tag)
            if args.artifact_dir:
                write_artifacts(
                    snapshot,
                    output_dir=Path(args.artifact_dir).expanduser(),
                    title=args.title,
                    version=args.version,
                    tag=args.tag,
                )
            write_output(draft, args.output)
            return 0
        if args.command == "artifacts":
            written = write_artifacts(
                snapshot,
                output_dir=Path(args.output_dir).expanduser(),
                title=args.title,
                version=args.version,
                tag=args.tag,
            )
            print("\n".join(str(path) for path in written))
            return 0
        entry = render_changelog_entry(snapshot, version=args.version, tag=args.tag, entry_date=args.date)
        if args.write:
            changelog_path = Path(args.file).expanduser()
            if not changelog_path.is_absolute():
                changelog_path = Path(snapshot.repo_root) / changelog_path
            existing = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""
            changelog_path.write_text(update_changelog_text(existing, entry), encoding="utf-8")
            print(str(changelog_path))
            return 0
        print(entry, end="")
        return 0
    if args.command == "apply":
        return run_apply(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
