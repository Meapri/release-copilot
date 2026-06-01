#!/usr/bin/env python3
"""Collect release context and draft release artifacts from a local git repo."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import shlex
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
    status_short: str
    changed_files: str
    diff_stat: str
    commits: str
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
    return ReleaseSnapshot(
        repo_root=str(repo),
        branch=git_output(repo, ["branch", "--show-current"]),
        head=git_output(repo, ["rev-parse", "--short", head_ref]),
        base_ref=base,
        latest_tag=latest_tag(repo),
        compare_range=diff_range[0] if diff_range else "working tree",
        status_short=git_output(repo, ["status", "--short"]),
        changed_files=git_output(repo, ["diff", "--name-status", *diff_range]),
        diff_stat=git_output(repo, ["diff", "--stat", *diff_range]),
        commits=git_output(repo, ["log", "--oneline", *log_range]),
        versions=version_infos(repo),
        checks=check_results,
    )


def parse_change_lines(snapshot: ReleaseSnapshot) -> list[str]:
    lines: list[str] = []
    for commit in snapshot.commits.splitlines():
        text = commit.strip()
        if not text:
            continue
        text = re.sub(r"^[0-9a-f]{6,40}\s+", "", text)
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


def render_draft(snapshot: ReleaseSnapshot, *, title: str = "", version: str = "", tag: str = "") -> str:
    change_lines = parse_change_lines(snapshot)
    release_title = title or f"Release {version or tag or snapshot.head}"
    version_text = version_summary(snapshot, version)
    tag_text = tag or (f"v{version}" if version else "[tag not selected]")

    sections = [
        "# Release Copilot Draft",
        "## Snapshot",
        f"- Repository: `{snapshot.repo_root}`",
        f"- Branch: `{snapshot.branch or '[detached]'}`",
        f"- Head: `{snapshot.head}`",
        f"- Base: `{snapshot.base_ref or '[not detected]'}`",
        f"- Compare range: `{snapshot.compare_range}`",
        f"- Latest tag: `{snapshot.latest_tag or '[none]'}`",
        f"- Version: `{version_text}`",
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
        "### Validation",
        check_summary(snapshot.checks),
        "",
        "### Reviewer Notes",
        "- [ ] Confirm version, migration, and compatibility notes.",
        "- [ ] Confirm no secrets or private data are included in release artifacts.",
        "",
        "## Release Notes Draft",
        f"### {release_title}",
        markdown_list(change_lines, "Describe user-facing changes."),
        "",
        "### Compatibility",
        "- [ ] Add breaking changes, migration notes, or mark as none.",
        "",
        "## Changelog Entry Draft",
        f"## {tag_text} - [date]",
        "### Changed",
        markdown_list(change_lines, "Describe notable changes."),
        "",
        "## Suggested Dry-Run Commands",
        f"- Tag: `python3 scripts/release_copilot.py apply --tag {shlex.quote(tag_text)} --dry-run`",
        "- GitHub release: `python3 scripts/release_copilot.py apply --github-release --notes-file RELEASE_NOTES.md --dry-run`",
    ]
    return "\n".join(sections).strip() + "\n"


def snapshot_to_json(snapshot: ReleaseSnapshot) -> str:
    return json.dumps(asdict(snapshot), ensure_ascii=False, indent=2)


def write_output(text: str, output: str) -> None:
    if output:
        Path(output).expanduser().write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def planned_apply_commands(args: argparse.Namespace) -> list[list[str]]:
    commands: list[list[str]] = []
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
    if not args.execute:
        print(render_commands(commands), end="")
        return 0
    for command in commands:
        print("$ " + " ".join(shlex.quote(part) for part in command), file=sys.stderr)
        proc = subprocess.run(command, cwd=str(repo), check=False)
        if proc.returncode != 0:
            return proc.returncode
    return 0


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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command in {"snapshot", "draft"}:
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
        write_output(
            render_draft(snapshot, title=args.title, version=args.version, tag=args.tag),
            args.output,
        )
        return 0
    if args.command == "apply":
        return run_apply(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
