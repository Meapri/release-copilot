from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PLUGIN_ROOT / "scripts" / "release_copilot.py"


def load_module():
    spec = importlib.util.spec_from_file_location("_release_copilot", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def init_repo(root: Path) -> None:
    run(["git", "init"], root)
    run(["git", "config", "user.name", "Test"], root)
    run(["git", "config", "user.email", "test@example.com"], root)
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / "package.json").write_text('{"version": "1.2.3"}\n', encoding="utf-8")
    run(["git", "add", "."], root)
    run(["git", "commit", "-m", "Initial"], root)
    run(["git", "tag", "v1.2.2"], root)
    (root / "README.md").write_text("# Demo\n\nUpdated release docs.\n", encoding="utf-8")
    run(["git", "add", "README.md"], root)
    run(["git", "commit", "-m", "Update release docs"], root)


class ReleaseCopilotTests(unittest.TestCase):
    def test_collect_snapshot_detects_versions_and_commits(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)

            snapshot = module.collect_snapshot(repo=root, base_ref="v1.2.2")

        self.assertEqual(snapshot.latest_tag, "v1.2.2")
        self.assertIn("Update release docs", snapshot.commits)
        self.assertEqual(snapshot.versions[0].path, "package.json")
        self.assertEqual(snapshot.versions[0].version, "1.2.3")

    def test_render_draft_contains_release_sections(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            snapshot = module.collect_snapshot(repo=root, base_ref="v1.2.2")

            draft = module.render_draft(snapshot, version="1.2.3", tag="v1.2.3")

        self.assertIn("# Release Copilot Draft", draft)
        self.assertIn("## PR Description Draft", draft)
        self.assertIn("## Release Notes Draft", draft)
        self.assertIn("Update release docs", draft)

    def test_check_command_records_failure(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)

            snapshot = module.collect_snapshot(
                repo=root,
                base_ref="v1.2.2",
                checks=["python3 -c 'import sys; sys.exit(3)'"],
            )

        self.assertEqual(snapshot.checks[0].exit_code, 3)
        self.assertIn("failed with exit code 3", module.check_summary(snapshot.checks))

    def test_apply_is_dry_run_by_default(self):
        module = load_module()
        args = SimpleNamespace(
            tag="v1.2.3",
            title="Release 1.2.3",
            message="",
            push_tag=True,
            github_release=True,
            notes_file="RELEASE_NOTES.md",
            notes="",
        )

        commands = module.render_commands(module.planned_apply_commands(args))

        self.assertIn("git tag -a v1.2.3", commands)
        self.assertIn("git push origin v1.2.3", commands)
        self.assertIn("gh release create v1.2.3", commands)

    def test_cli_draft_outputs_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "draft",
                    "--repo",
                    str(root),
                    "--base",
                    "v1.2.2",
                    "--version",
                    "1.2.3",
                ],
                check=False,
                text=True,
                capture_output=True,
            )

        self.assertEqual(proc.returncode, 0)
        self.assertIn("Release Copilot Draft", proc.stdout)
        self.assertIn("Update release docs", proc.stdout)


if __name__ == "__main__":
    unittest.main()
