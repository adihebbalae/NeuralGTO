"""
solver_runner.py — Step 3: Execute TexasSolver Binary.

Runs the TexasSolver console binary with the generated input file.
Falls back to GPT-only mode if the binary is not available.

Created: 2026-02-06

DOCUMENTATION:
- Input: Path to the solver input file (from solver_input.py)
- Output: Path to the solver JSON output file
- The binary is run as a subprocess with a configurable timeout
- Console binary usage: console.exe -i input.txt -r resources/ -m holdem
- If binary is not found, returns None (caller should use fallback)
"""

import subprocess
from pathlib import Path

from poker_gpt import config


def _platform_solver_message() -> str:
    """Return a platform-specific message when the solver binary is missing."""
    binary = Path(config.SOLVER_BINARY_PATH)
    if config.IS_WINDOWS:
        return (
            f"[SOLVER_RUNNER] Windows solver (console_solver.exe) "
            f"not found at: {binary}\n"
            f"[SOLVER_RUNNER] Download from https://github.com/bupticybee/TexasSolver/releases"
        )
    elif config.IS_LINUX:
        return (
            f"[SOLVER_RUNNER] Linux solver (console_solver) "
            f"not found at: {binary}\n"
            f"[SOLVER_RUNNER] Download the Linux release from "
            f"https://github.com/bupticybee/TexasSolver/releases\n"
            f"[SOLVER_RUNNER] Ensure the binary has execute permissions: chmod +x {binary.name}"
        )
    else:  # macOS / Darwin
        return (
            f"[SOLVER_RUNNER] macOS solver (console_solver) "
            f"not found at: {binary}\n"
            f"[SOLVER_RUNNER] Download the macOS/Linux release from "
            f"https://github.com/bupticybee/TexasSolver/releases\n"
            f"[SOLVER_RUNNER] Ensure the binary has execute permissions: chmod +x {binary.name}"
        )


def run_solver(input_file: Path = None, timeout: int = None) -> Path | None:
    """
    Execute the TexasSolver binary with the given input file.
    
    Args:
        input_file: Path to the solver command file. Defaults to config.SOLVER_INPUT_FILE.
        timeout: Override timeout in seconds. None = use config default.
        
    Returns:
        Path to the output JSON file if successful, None if solver is unavailable.
        
    Raises:
        RuntimeError: If the solver binary exists but fails to execute.
    """
    _timeout = timeout if timeout is not None else config.SOLVER_TIMEOUT
    if input_file is None:
        input_file = config.SOLVER_INPUT_FILE
    
    input_file = Path(input_file)
    binary_path = Path(config.SOLVER_BINARY_PATH)
    resources_path = Path(config.SOLVER_RESOURCES_PATH)

    # SECURITY: Verify solver binary is within the expected solver_bin/ directory
    # Prevents arbitrary binary execution via SOLVER_BINARY_PATH env var manipulation
    _project_root = Path(__file__).parent.parent
    _allowed_solver_dir = _project_root / "solver_bin"
    try:
        binary_path.resolve().relative_to(_allowed_solver_dir.resolve())
    except ValueError:
        print(
            f"[SOLVER_RUNNER] SECURITY: Solver binary path ({binary_path}) "
            f"is outside the allowed directory ({_allowed_solver_dir}). Refusing to execute."
        )
        return None
    
    # Check if solver binary exists
    if not binary_path.exists():
        msg = _platform_solver_message()
        print(msg)
        print("[SOLVER_RUNNER] Will use GPT-only fallback mode.")
        return None
    
    if not resources_path.exists():
        print(f"[SOLVER_RUNNER] Resources directory not found at: {resources_path}")
        return None
    
    if not input_file.exists():
        raise RuntimeError(f"Solver input file not found: {input_file}")
    
    # Delete stale output file before running solver
    output_file = config.SOLVER_OUTPUT_FILE
    if output_file.exists():
        output_file.unlink()
    
    # Build command
    cmd = [
        str(binary_path),
        "-i", str(input_file),
        "-r", str(resources_path),
        "-m", config.SOLVER_MODE,
    ]
    
    if config.DEBUG:
        print(f"[SOLVER_RUNNER] Running command: {' '.join(cmd)}")
    
    # Execute solver
    try:
        print("[SOLVER_RUNNER] Starting solver... (this may take 1-5 minutes)")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_timeout,
            cwd=str(binary_path.parent),  # Run from the binary's directory
        )
        
        if config.DEBUG:
            print(f"[SOLVER_RUNNER] stdout:\n{result.stdout[-500:]}")  # Last 500 chars
            if result.stderr:
                print(f"[SOLVER_RUNNER] stderr:\n{result.stderr[-500:]}")
        
        if result.returncode != 0:
            raise RuntimeError(
                f"Solver exited with code {result.returncode}.\n"
                f"stderr: {result.stderr[-500:]}"
            )
        
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Solver timed out after {_timeout}s. "
            "Try reducing max_iterations or increasing accuracy tolerance."
        )
    except FileNotFoundError:
        print(f"[SOLVER_RUNNER] Could not execute binary: {binary_path}")
        return None
    
    # Check output file
    output_file = config.SOLVER_OUTPUT_FILE
    if output_file.exists() and output_file.stat().st_size > 0:
        print(f"[SOLVER_RUNNER] Solver completed. Output: {output_file}")
        return output_file
    else:
        raise RuntimeError(
            "Solver completed but output file is empty or missing. "
            f"Expected at: {output_file}"
        )


def is_solver_available() -> bool:
    """Check if the solver binary is available and can run.

    Checks for the platform-appropriate binary name:
      - Windows: console_solver.exe
      - Linux/Mac: console_solver

    Returns:
        True if both the binary and resources directory exist.
    """
    binary_path = Path(config.SOLVER_BINARY_PATH)
    resources_path = Path(config.SOLVER_RESOURCES_PATH)
    available = binary_path.exists() and resources_path.exists()
    if not available and config.DEBUG:
        print(_platform_solver_message())
    return available
