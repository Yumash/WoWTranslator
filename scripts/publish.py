"""Publish clean version to public GitHub repo.

Copies the project excluding private dev files (.claude, .claude-lib, etc.)
and pushes to github.com/Yumash/WoWTranslator.

Usage:
    python scripts/publish.py --version 1.0.0
    python scripts/publish.py --version 1.0.0 --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Root of the dev repo (parent of scripts/)
REPO_ROOT = Path(__file__).resolve().parent.parent

PUBLIC_REMOTE = "https://github.com/Yumash/WoWTranslator.git"

# Patterns to EXCLUDE from the public release
EXCLUDE_DIRS = {
    ".claude",
    ".claude-lib",
    ".claude-project",
    ".rag",
    ".venv",
    "venv",
    "dist",
    "build",
    "temp",
    "AutoChatLog",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    ".gitmodules",
    "node_modules",
}

EXCLUDE_FILES = {
    "config.json",
    "debug.log",
    "wct_app.log",
    "wct_raw.log",
    "overlay_settings.json",
    "settings_dialog_pos.json",
    "CLAUDE.md",
    "build.bat",
    "translations.db",
    ".mcp.json",
    ".gitmodules",
    "RESEARCH.md",
    "EVALUATION.md",
}

EXCLUDE_EXTENSIONS = {
    ".log",
    ".db",
    ".pyc",
    ".pyo",
}

# Clean .gitignore for the public repo
PUBLIC_GITIGNORE = """\
# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.venv/
venv/

# Build
build/
dist/

# Runtime
config.json
*.log
*.db
.env
overlay_settings.json
settings_dialog_pos.json
"""


def should_exclude(path: Path, rel: Path) -> bool:
    """Check if a path should be excluded from the public release."""
    name = path.name

    # Exclude hidden dirs/files (except .github, .env.example, .gitignore)
    if name.startswith(".") and name not in {".github", ".env.example", ".gitignore"}:
        if path.is_dir():
            return True
        # Allow .env.example but not .env
        if name == ".env":
            return True

    # Check directory exclusions
    for part in rel.parts:
        if part in EXCLUDE_DIRS:
            return True

    # Check file exclusions
    if path.is_file():
        if name in EXCLUDE_FILES:
            return True
        if path.suffix in EXCLUDE_EXTENSIONS:
            return True

    return False


def copy_tree(src: Path, dst: Path) -> int:
    """Copy source tree to destination, excluding private files. Returns file count."""
    count = 0
    for item in sorted(src.iterdir()):
        rel = item.relative_to(REPO_ROOT)
        if should_exclude(item, rel):
            continue

        dest = dst / item.name
        if item.is_dir():
            dest.mkdir(exist_ok=True)
            count += copy_tree(item, dest)
        else:
            shutil.copy2(item, dest)
            count += 1
    return count


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and print it."""
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish clean version to public GitHub")
    parser.add_argument("--version", required=True, help="Version tag (e.g. 1.0.0)")
    parser.add_argument("--dry-run", action="store_true", help="Build but don't push")
    parser.add_argument("--message", default="", help="Custom commit message")
    args = parser.parse_args()

    version = args.version
    tag = f"v{version}"
    commit_msg = args.message or f"Release {tag}"

    print(f"Publishing WoWTranslator {tag}")
    print(f"  Source: {REPO_ROOT}")
    print(f"  Remote: {PUBLIC_REMOTE}")
    print(f"  Dry run: {args.dry_run}")
    print()

    # Create temp directory
    with tempfile.TemporaryDirectory(prefix="wct-publish-") as tmp:
        tmp_path = Path(tmp)
        pub_dir = tmp_path / "WoWTranslator"
        pub_dir.mkdir()

        # Copy files
        print("Copying files (excluding private dev stack)...")
        count = copy_tree(REPO_ROOT, pub_dir)
        print(f"  Copied {count} files")

        # Write clean .gitignore
        (pub_dir / ".gitignore").write_text(PUBLIC_GITIGNORE, encoding="utf-8")

        if args.dry_run:
            print("\n--- DRY RUN: Files that would be published ---")
            for f in sorted(pub_dir.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(pub_dir)
                    size = f.stat().st_size
                    print(f"  {rel}  ({size:,} bytes)")
            print(f"\nTotal: {count} files")
            print("Dry run complete — nothing was pushed.")
            return 0

        # Init git and commit
        print("\nInitializing git...")
        run(["git", "init", "-b", "main"], cwd=pub_dir)
        run(["git", "add", "-A"], cwd=pub_dir)
        run(["git", "commit", "-m", commit_msg], cwd=pub_dir)
        run(["git", "tag", tag], cwd=pub_dir)

        # Push
        print(f"\nPushing to {PUBLIC_REMOTE}...")
        run(["git", "remote", "add", "origin", PUBLIC_REMOTE], cwd=pub_dir)
        run(["git", "push", "-f", "origin", "main"], cwd=pub_dir)
        run(["git", "push", "origin", tag], cwd=pub_dir)

        print(f"\nPublished {tag} to {PUBLIC_REMOTE}")
        print("Done!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
