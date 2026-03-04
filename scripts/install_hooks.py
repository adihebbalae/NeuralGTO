#!/usr/bin/env python3
"""
scripts/install_hooks.py — Install NeuralGTO git hooks into .git/hooks/.

Run once after cloning or whenever hooks need to be refreshed:
  python scripts/install_hooks.py

What it installs:
  .git/hooks/pre-commit  →  calls scripts/pre-commit-check.py
  .git/hooks/pre-push    →  runs offline test suite + forbidden-file check
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


PRE_PUSH_HOOK = """\
#!/usr/bin/env bash
# NeuralGTO pre-push hook -- installed by scripts/install_hooks.py
# To update: python scripts/install_hooks.py
#
# Runs before every git push. Blocks the push if:
#   1. Forbidden files (_priv/, _dev/, .github/, .env, solver_bin/) are staged
#   2. The offline test suite fails

REPO_ROOT="$(git rev-parse --show-toplevel)"

# -- 1. Forbidden-file check ------------------------------------------------
FORBIDDEN=("_priv/" "_dev/" ".github/" ".env" "solver_bin/")
for item in "${FORBIDDEN[@]}"; do
  if git diff --name-only "@{push}" HEAD 2>/dev/null | grep -q "${item}" || \\
     git diff --cached --name-only 2>/dev/null | grep -q "${item}"; then
    echo "ERROR: Forbidden path staged for push: ${item}" >&2
    echo "Run: git reset HEAD -- <file> to unstage, then retry." >&2
    exit 1
  fi
done

# -- 2. Find a Python that has pytest ----------------------------------------
# Try the project venv first (handles both Windows git-bash and Unix paths),
# then fall back to system Python.
cd "${REPO_ROOT}" || exit 1

PYTHON=""
for candidate in \\
    ".venv/Scripts/python.exe" \\
    ".venv/bin/python" \\
    "backend/.venv/Scripts/python.exe" \\
    "backend/.venv/bin/python"; do
  if [[ -x "${REPO_ROOT}/${candidate}" ]]; then
    PYTHON="${REPO_ROOT}/${candidate}"
    break
  fi
done

if [[ -z "${PYTHON}" ]]; then
  for py in python3 python py; do
    if command -v "$py" &>/dev/null; then
      PYTHON="$py"
      break
    fi
  done
fi

if [[ -z "${PYTHON}" ]]; then
  echo "WARNING: Python not found -- cannot run tests. Allowing push." >&2
  exit 0
fi

if ! "${PYTHON}" -m pytest --version &>/dev/null; then
  echo "WARNING: pytest not found in ${PYTHON} -- skipping test gate." >&2
  exit 0
fi

# -- 3. Run offline test suite -----------------------------------------------
echo "[pre-push] Running offline tests with ${PYTHON}..."
"${PYTHON}" -m pytest poker_gpt/tests/ -q -k "not test_full_pipeline_with_api" 2>&1
TEST_EXIT=$?
if [[ ${TEST_EXIT} -ne 0 ]]; then
  echo "" >&2
  echo "ERROR: Tests failed -- push blocked." >&2
  echo "Fix the failures above, then retry git push." >&2
  exit 1
fi
echo "[pre-push] All offline tests passed."
exit 0
"""


def _install_hook(hooks_dir: "Path", hook_name: str, hook_content: str, description: str) -> None:
    hook_path = hooks_dir / hook_name
    if hook_path.exists():
        existing = hook_path.read_text()
        if "NeuralGTO" in existing:
            print(f"  Re-installing {hook_name} to pick up latest content...")
        else:
            print(f"WARNING: A {hook_name} hook already exists at {hook_path}")
            print("  It does NOT appear to be the NeuralGTO hook.")
            answer = input("  Overwrite? [y/N] ").strip().lower()
            if answer != "y":
                print(f"Skipped {hook_name}.")
                return
    hook_path.write_text(hook_content)
    current_mode = hook_path.stat().st_mode
    hook_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"✓ Installed {hook_name} → {hook_path}")
    print(f"  Validates: {description}")


def install() -> int:
    try:
        repo_root = find_repo_root()
    except subprocess.CalledProcessError:
        print("ERROR: Not inside a git repository.", file=sys.stderr)
        return 1

    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Legacy single-hook path: handle existing pre-commit without NeuralGTO tag
    pre_commit_path = hooks_dir / "pre-commit"
    if pre_commit_path.exists() and "pre-commit-check.py" in pre_commit_path.read_text():
        print(f"✓ pre-commit hook already installed at {pre_commit_path}")
        print("  Re-installing to pick up latest content...")

    _install_hook(
        hooks_dir, "pre-commit", PRE_COMMIT_HOOK,
        "hardcoded secrets | dangerous builtins | forbidden files",
    )
    _install_hook(
        hooks_dir, "pre-push", PRE_PUSH_HOOK,
        "forbidden files in push set | offline test suite",
    )

    print("\nTo test the pre-commit hook manually:")
    print("  python scripts/pre-commit-check.py")
    return 0


if __name__ == "__main__":
    sys.exit(install())
