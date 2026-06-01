#!/usr/bin/env python3
"""Install Release Copilot into Codex from this repository checkout."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys


PLUGIN_NAME = "release-copilot"
MARKETPLACE_NAME = "personal"
MARKETPLACE_DISPLAY_NAME = "Personal"
CATEGORY = "Productivity"


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, check=False)


def personal_marketplace_path(home: Path) -> Path:
    return home / ".agents" / "plugins" / "marketplace.json"


def local_source_path(repo_root: Path, home: Path) -> str:
    try:
        relative = repo_root.resolve().relative_to(home.resolve())
    except ValueError as exc:
        raise ValueError(
            f"{PLUGIN_NAME} must be inside {home} so Codex can install it from the personal marketplace."
        ) from exc
    return f"./{relative.as_posix()}"


def personal_marketplace_entry(repo_root: Path, home: Path) -> dict[str, object]:
    return {
        "name": PLUGIN_NAME,
        "source": {
            "source": "local",
            "path": local_source_path(repo_root, home),
        },
        "policy": {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        },
        "category": CATEGORY,
    }


def read_marketplace(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "name": MARKETPLACE_NAME,
            "interface": {"displayName": MARKETPLACE_DISPLAY_NAME},
            "plugins": [],
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Marketplace file must contain a JSON object: {path}")
    return data


def upsert_personal_marketplace(data: dict[str, object], entry: dict[str, object]) -> dict[str, object]:
    name = data.setdefault("name", MARKETPLACE_NAME)
    if name != MARKETPLACE_NAME:
        raise ValueError(
            f"Expected personal marketplace name {MARKETPLACE_NAME!r}, found {name!r}. "
            "Install from the default personal marketplace or update the script for your custom marketplace."
        )

    interface = data.setdefault("interface", {"displayName": MARKETPLACE_DISPLAY_NAME})
    if not isinstance(interface, dict):
        raise ValueError("Marketplace interface must be a JSON object.")
    interface.setdefault("displayName", MARKETPLACE_DISPLAY_NAME)

    plugins = data.setdefault("plugins", [])
    if not isinstance(plugins, list):
        raise ValueError("Marketplace plugins must be a JSON array.")

    for index, plugin in enumerate(plugins):
        if isinstance(plugin, dict) and plugin.get("name") == PLUGIN_NAME:
            plugins[index] = entry
            break
    else:
        plugins.append(entry)

    return data


def write_marketplace(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cleanup_legacy_repo_marketplace(codex: str, repo_root: Path) -> None:
    # Earlier prerelease installers tried to register the repository itself as a marketplace.
    # The supported public path is the personal marketplace entry generated above.
    removal = run([codex, "plugin", "marketplace", "remove", PLUGIN_NAME], cwd=repo_root)
    output = (removal.stdout + removal.stderr).strip()
    if removal.returncode == 0 and output:
        print(output)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    home = Path.home()
    codex = shutil.which("codex")
    if not codex:
        print("Codex CLI was not found on PATH. Open Codex or install the Codex CLI first.", file=sys.stderr)
        return 1

    plugin_manifest = repo_root / ".codex-plugin" / "plugin.json"
    if not plugin_manifest.exists():
        print(f"Missing plugin manifest: {plugin_manifest}", file=sys.stderr)
        return 1

    try:
        marketplace_file = personal_marketplace_path(home)
        entry = personal_marketplace_entry(repo_root, home)
        marketplace = upsert_personal_marketplace(read_marketplace(marketplace_file), entry)
        write_marketplace(marketplace_file, marketplace)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Could not update personal marketplace: {exc}", file=sys.stderr)
        return 1

    print(f"Updated personal marketplace: {marketplace_file}")
    cleanup_legacy_repo_marketplace(codex, repo_root)

    add_plugin = run([codex, "plugin", "add", f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"], cwd=repo_root)
    plugin_output = (add_plugin.stdout + add_plugin.stderr).strip()
    if add_plugin.returncode != 0:
        print(plugin_output, file=sys.stderr)
        return add_plugin.returncode
    if plugin_output:
        print(plugin_output)
    print("Release Copilot installed. Start a new Codex thread to load the refreshed skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
