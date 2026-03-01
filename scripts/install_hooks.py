#!/usr/bin/env python3
"""
scripts/install_hooks.py — Install NeuralGTO git hooks into .git/hooks/.

Run once after cloning or whenever hooks need to be refreshed:
  python scripts/install_hooks.py

What it installs:
  .git/hooks/pre-commit  →  calls scripts/pre-commit-check.py
"""

import os
import stat
import subprocess
import sys
from pathlib import Path


def find_repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(result.stdout.strip())


PRE_COMMIT_HOOK = """\
#!/usr/bin/env bash
# NeuralGTO pre-commit security hook — installed by scripts/install_hooks.py
# To update: python scripts/install_hooks.py

REPO_ROOT="$(git rev-parse --show-toplevel)"
SCRIPT="$REPO_ROOT/scripts/pre-commit-check.py"

if [ ! -f "$SCRIPT" ]; then
  echo "WARNING: pre-commit-check.py not found at $SCRIPT — skipping security checks." >&2
  exit 0
fi

# Try python, python3, py in order (handles Windows + Unix)
for py in python python3 py; do
  if command -v "$py" &>/dev/null; then
    "$py" "$SCRIPT"
    exit $?
  fi
done

echo "ERROR: Python not found in PATH — cannot run pre-commit security checks." >&2
echo "Install Python or run: git commit --no-verify (not recommended)" >&2
exit 1
"""


def install() -> int:
    try:
        repo_root = find_repo_root()
    except subprocess.CalledProcessError:
        print("ERROR: Not inside a git repository.", file=sys.stderr)
        return 1

    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    pre_commit_path = hooks_dir / "pre-commit"

    if pre_commit_path.exists():
        existing = pre_commit_path.read_text()
        if "pre-commit-check.py" in existing:
            print(f"✓ pre-commit hook already installed at {pre_commit_path}")
            print("  Re-installing to pick up latest content...")
        else:
            print(f"WARNING: A pre-commit hook already exists at {pre_commit_path}")
            print("  It does NOT appear to be the NeuralGTO hook.")
            answer = input("  Overwrite? [y/N] ").strip().lower()
            if answer != "y":
                print("Aborted.")
                return 1

    pre_commit_path.write_text(PRE_COMMIT_HOOK)

    # Make executable (required on Unix; harmless on Windows)
    current_mode = pre_commit_path.stat().st_mode
    pre_commit_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"✓ Installed pre-commit hook → {pre_commit_path}")
    print("  Validates: hardcoded secrets | dangerous builtins | forbidden files")
    print("\nTo test the hook manually:")
    print("  python scripts/pre-commit-check.py")
    return 0


if __name__ == "__main__":
    sys.exit(install())
