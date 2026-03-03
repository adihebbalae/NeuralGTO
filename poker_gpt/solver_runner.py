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
    # Design: use Popen + wait(timeout) rather than subprocess.run().
    # stdout=DEVNULL: TexasSolver prints one line per iteration — capturing
    # that pipe causes Python to hang draining it after a timeout kill.
    # We let the solver self-terminate via its own max_iterations setting;
    # _timeout is a generous safety net (default 1800s for overnight runs).
    # Because stdout is DEVNULL, post-kill wait() returns instantly.
    try:
        print("[SOLVER_RUNNER] Starting solver... (this may take 1-5 minutes)")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            cwd=str(binary_path.parent),
        )
        try:
            _, stderr_bytes = proc.communicate(timeout=_timeout)
            stderr_text = stderr_bytes.decode(errors="replace") if stderr_bytes else ""
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()  # instant — stdout is DEVNULL
            raise RuntimeError(
                f"Solver timed out after {_timeout}s. "
                "Increase timeout or reduce max_iterations."
            )

        if config.DEBUG and stderr_text:
            print(f"[SOLVER_RUNNER] stderr:\n{stderr_text[-500:]}")

        if proc.returncode != 0:
            raise RuntimeError(
                f"Solver exited with code {proc.returncode}.\n"
                f"stderr: {stderr_text[-500:]}"
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
        if config.DEBUG:
            print(
                f"[SOLVER_RUNNER] Solver completed but output file is empty or "
                f"missing. Expected at: {output_file}"
            )
        return None


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
