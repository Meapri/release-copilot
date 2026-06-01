from __future__ import annotations

import contextlib
import io
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PLUGIN_ROOT / "scripts" / "release_copilot.py"
INSTALL_SCRIPT_PATH = PLUGIN_ROOT / "scripts" / "install_plugin.py"


def load_module():
    spec = importlib.util.spec_from_file_location("_release_copilot", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_install_module():
    spec = importlib.util.spec_from_file_location("_release_copilot_installer", INSTALL_SCRIPT_PATH)
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
    run(["git", "commit", "-m", "docs: update release docs"], root)


def init_release_tool_files(root: Path) -> None:
    (root / ".changeset").mkdir()
    (root / ".changeset" / "config.json").write_text("{}\n", encoding="utf-8")
    (root / ".goreleaser.yaml").write_text("version: 2\n", encoding="utf-8")
    (root / "release-please-config.json").write_text("{}\n", encoding="utf-8")
    (root / ".releaserc.json").write_text("{}\n", encoding="utf-8")


class ReleaseCopilotTests(unittest.TestCase):
    def test_collect_snapshot_detects_versions_and_commits(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)

            snapshot = module.collect_snapshot(repo=root, base_ref="v1.2.2")

        self.assertEqual(snapshot.latest_tag, "v1.2.2")
        self.assertIn("docs: update release docs", snapshot.commits)
        self.assertEqual(snapshot.versions[0].path, "package.json")
        self.assertEqual(snapshot.versions[0].version, "1.2.3")
        self.assertEqual(snapshot.recommended_bump, "patch")
        self.assertEqual(snapshot.recommended_version, "1.2.4")
        self.assertEqual(snapshot.change_categories["docs"], ["update release docs"])
        self.assertEqual(snapshot.release_tools, [])

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
        self.assertIn("### Documentation", draft)
        self.assertIn("update release docs", draft)
        self.assertIn("Recommended next version: `1.2.4`", draft)
        self.assertIn("Detected release tools:", draft)

    def test_detect_release_tools(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            init_release_tool_files(root)

            tools = module.detect_release_tools(root)

        self.assertEqual(tools, ["semantic-release", "release-please", "changesets", "goreleaser"])

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

    def test_github_release_requires_tag(self):
        module = load_module()
        args = SimpleNamespace(
            tag="",
            title="Release 1.2.3",
            message="",
            push_tag=False,
            github_release=True,
            notes_file="RELEASE_NOTES.md",
            notes="",
        )

        with self.assertRaises(SystemExit):
            module.planned_apply_commands(args)

    def test_dry_run_overrides_execute(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            args = SimpleNamespace(
                repo=str(root),
                tag="v9.9.9",
                title="",
                message="",
                push_tag=False,
                github_release=False,
                notes_file="",
                notes="",
                execute=True,
                dry_run=True,
                allow_dirty=False,
            )

            with contextlib.redirect_stdout(io.StringIO()):
                code = module.run_apply(args)

        self.assertEqual(code, 0)

    def test_changelog_update_inserts_after_title(self):
        module = load_module()
        entry = "## v1.2.3 - 2026-06-01\n\n### Fixed\n- Bug\n"

        updated = module.update_changelog_text("# Changelog\n\n## old\n\n- Old\n", entry)

        self.assertTrue(updated.startswith("# Changelog\n\n## v1.2.3 - 2026-06-01"))
        self.assertIn("## old", updated)

    def test_changed_files_fallback_when_no_commits(self):
        module = load_module()

        categories = module.categorize_changed_files("M\tREADME.md\nA\tCHANGELOG.md\n")

        self.assertEqual(categories["other"], ["M\tREADME.md", "A\tCHANGELOG.md"])

    def test_dirty_working_tree_falls_back_to_status_when_range_is_empty(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            (root / "UNTRACKED.md").write_text("draft\n", encoding="utf-8")

            snapshot = module.collect_snapshot(repo=root, base_ref=head)

        self.assertIn("UNTRACKED.md", snapshot.changed_files)
        self.assertIn("UNTRACKED.md", snapshot.change_categories["other"][0])

    def test_artifacts_write_expected_files(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repo(root)
            snapshot = module.collect_snapshot(repo=root, base_ref="v1.2.2")
            output_dir = Path(tmp) / "artifacts"

            written = module.write_artifacts(snapshot, output_dir=output_dir, version="1.2.4", tag="v1.2.4")

        names = {path.name for path in written}
        self.assertIn("PR_DESCRIPTION.md", names)
        self.assertIn("RELEASE_NOTES.md", names)
        self.assertIn("CHANGELOG_ENTRY.md", names)
        self.assertIn("RELEASE_SNAPSHOT.json", names)

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
        self.assertIn("update release docs", proc.stdout)

    def test_cli_changelog_outputs_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "changelog",
                    "--repo",
                    str(root),
                    "--base",
                    "v1.2.2",
                    "--version",
                    "1.2.4",
                    "--tag",
                    "v1.2.4",
                    "--date",
                    "2026-06-01",
                ],
                check=False,
                text=True,
                capture_output=True,
            )

        self.assertEqual(proc.returncode, 0)
        self.assertIn("## v1.2.4 - 2026-06-01", proc.stdout)
        self.assertIn("### Documentation", proc.stdout)

    def test_cli_doctor_outputs_detected_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            init_release_tool_files(root)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "doctor",
                    "--repo",
                    str(root),
                ],
                check=False,
                text=True,
                capture_output=True,
            )

        self.assertEqual(proc.returncode, 0)
        self.assertIn("Detected release tools: semantic-release, release-please, changesets, goreleaser", proc.stdout)


class ReleaseCopilotInstallerTests(unittest.TestCase):
    def test_personal_marketplace_entry_uses_home_relative_path(self):
        module = load_install_module()
        home = Path("/Users/tester")
        repo = home / "plugins" / "release-copilot"

        entry = module.personal_marketplace_entry(repo, home)

        self.assertEqual(entry["name"], "release-copilot")
        self.assertEqual(entry["source"]["path"], "./plugins/release-copilot")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")

    def test_personal_marketplace_entry_rejects_external_repo(self):
        module = load_install_module()

        with self.assertRaises(ValueError):
            module.personal_marketplace_entry(Path("/opt/release-copilot"), Path("/Users/tester"))

    def test_upsert_personal_marketplace_preserves_existing_entries(self):
        module = load_install_module()
        data = {
            "name": "personal",
            "interface": {"displayName": "My Plugins"},
            "plugins": [
                {"name": "other-plugin", "source": {"source": "local", "path": "./plugins/other-plugin"}},
                {"name": "release-copilot", "source": {"source": "local", "path": "./old"}},
            ],
        }
        entry = module.personal_marketplace_entry(
            Path("/Users/tester/plugins/release-copilot"),
            Path("/Users/tester"),
        )

        updated = module.upsert_personal_marketplace(data, entry)

        self.assertEqual(updated["interface"]["displayName"], "My Plugins")
        self.assertEqual(len(updated["plugins"]), 2)
        self.assertEqual(updated["plugins"][0]["name"], "other-plugin")
        self.assertEqual(updated["plugins"][1]["source"]["path"], "./plugins/release-copilot")


if __name__ == "__main__":
    unittest.main()
