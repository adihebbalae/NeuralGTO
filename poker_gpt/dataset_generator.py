"""
Dataset Generator for NeuralGTO

Generates diverse poker scenarios, solves them with TexasSolver, and saves results.
This builds a training corpus for future neural solver approximation and provides
a benchmark suite for accuracy testing.

Created: February 27, 2026

DOCUMENTATION:
    Run this as a standalone script:
        python -m poker_gpt.dataset_generator --num-scenarios 100 --mode default
        python -m poker_gpt.dataset_generator --resume
    
    Features:
    - Generates random but realistic poker scenarios
    - Solves each with TexasSolver (skips if solver unavailable)
    - Saves both solver output and extracted strategy
    - Progress bar + ETA
    - Checkpoint/resume support
    - Statistics summary

    Output: poker_gpt/_work/training_data/
        - scenarios.jsonl (one scenario per line)
        - DATASET_STATS.txt (summary statistics)
        - checkpoint.json (resume state)
"""

import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import argparse

from poker_gpt import config
from poker_gpt.poker_types import ScenarioData, Street, Position, StrategyResult
from poker_gpt.solver_input import create_solver_input
from poker_gpt.solver_runner import run_solver, is_solver_available
from poker_gpt.strategy_extractor import extract_strategy


# Scenario generation parameters
POSITIONS = [Position.BTN, Position.CO, Position.MP, Position.SB, Position.BB, Position.UTG]
STREETS = [Street.FLOP, Street.TURN, Street.RIVER]
STACK_DEPTHS = [20, 30, 40, 50, 75, 100, 150, 200]  # in BB
POT_SIZES_BB = [3, 5, 8, 12, 15, 20, 30, 40]

# Board texture templates
BOARD_TEMPLATES = {
    Street.FLOP: [
        "AhKsQc",  # broadway dry
        "Ts9d4h",  # medium connected
        "7h6h5s",  # coordinated draw-heavy
        "Kd9s2c",  # K-high dry
        "QhQd4s",  # paired
        "Jh8h3h",  # monotone flush
        "9c8c7d",  # straight possible
        "Ad5s2h",  # ace-high dry
        "KhThJh",  # flush draw + straight draw
        "2s2h2d",  # trips
    ],
    Street.TURN: [
        "AhKsQcJd",
        "Ts9d4h3s",
        "7h6h5s2d",
        "Kd9s2c8h",
        "QhQd4s9c",
        "Jh8h3h5h",  # 4-flush
        "9c8c7d6s",  # 4-straight
        "Ad5s2h7c",
    ],
    Street.RIVER: [
        "AhKsQcJdTc",
        "Ts9d4h3s2h",
        "7h6h5s2dKc",
        "Kd9s2c8h4s",
        "QhQd4s9c3h",
        "Jh8h3h5h9h",  # flush complete
        "9c8c7d6s5h",  # straight complete
    ]
}

# Hand templates (hero ranges)
HAND_EXAMPLES = [
    "AsAh", "KsKh", "QhQd", "JsJh", "TsTh",  # premium pairs
    "AhKs", "AhQs", "AdJd", "AcTc",  # broadway suited
    "AhKd", "AhQc", "KdQh",  # broadway offsuit
    "9h8h", "8c7c", "7s6s", "6h5h",  # suited connectors
    "AdJh", "KdJh", "QdTh",  # broadway offsuit gappers
    "AhTd", "Ah9d", "Kh9s",  # offsuit broadways
]

# Villain range templates
RANGE_TEMPLATES = [
    "AA,KK,QQ,JJ,TT,99,88,AKs,AQs,AJs,ATs,KQs,KJs,AKo,AQo",  # tight value
    "22+,ATs+,KTs+,QTs+,JTs,T9s,98s,87s,AJo+,KQo",  # standard open
    "22+,A2s+,K9s+,Q9s+,J9s+,T8s+,97s+,86s+,75s+,64s+,54s,A9o+,KTo+,QTo+,JTo",  # wide
    "AA-TT,AKs,AQs,AJs,KQs,AKo,AQo",  # 3bet range
    "QQ+,AKs,AKo",  # 4bet range (tight)
]


def generate_random_scenario() -> ScenarioData:
    """Generate a random but realistic poker scenario."""
    street = random.choice(STREETS)
    board = random.choice(BOARD_TEMPLATES[street])
    hero_pos = random.choice(POSITIONS)
    
    # Villain position (ensure different from hero, and realistic)
    villain_candidates = [p for p in POSITIONS if p != hero_pos]
    villain_pos = random.choice(villain_candidates)
    
    # Determine who is in position (BTN > CO > MP > UTG > BB > SB in postflop)
    position_order = {Position.BTN: 0, Position.CO: 1, Position.MP: 2, 
                     Position.UTG: 3, Position.BB: 4, Position.SB: 5}
    hero_is_ip = position_order.get(hero_pos, 3) < position_order.get(villain_pos, 3)
    
    stack = random.choice(STACK_DEPTHS)
    pot = random.choice(POT_SIZES_BB)
    
    hero_hand = random.choice(HAND_EXAMPLES)
    villain_range = random.choice(RANGE_TEMPLATES)
    hero_range = random.choice(RANGE_TEMPLATES)
    
    return ScenarioData(
        hero_hand=hero_hand,
        hero_position=hero_pos.value,
        hero_is_ip=hero_is_ip,
        villain_position=villain_pos.value,
        board=board,
        current_street=street.value,
        pot_size_bb=pot,
        effective_stack_bb=stack,
        villain_range=villain_range,
        hero_range=hero_range,
        actions_history=[],
        opponent_notes="",
    )


def solve_scenario(scenario: ScenarioData, mode: str = "default") -> Optional[dict]:
    """
    Solve a scenario and return results.
    
    Returns:
        dict with keys: scenario, solver_output_path, strategy, solve_time, success
        None if solver is unavailable
    """
    if not is_solver_available():
        return None
    
    start_time = time.time()
    
    try:
        # Create solver input
        input_file = create_solver_input(scenario, mode=mode)
        
        # Run solver
        output_file = run_solver(input_file, timeout_seconds=config.MODE_PRESETS[mode]["timeout"])
        
        if output_file is None:
            return {
                "scenario": scenario.to_dict(),
                "solver_output_path": None,
                "strategy": None,
                "solve_time": time.time() - start_time,
                "success": False,
                "error": "Solver returned None",
            }
        
        # Extract strategy
        strategy = extract_strategy(output_file, scenario.hero_hand)
        
        solve_time = time.time() - start_time
        
        return {
            "scenario": scenario.to_dict(),
            "solver_output_path": str(output_file),
            "strategy": strategy.to_dict(),
            "solve_time": solve_time,
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
        }
        
    except Exception as e:
        return {
            "scenario": scenario.to_dict(),
            "solver_output_path": None,
            "strategy": None,
            "solve_time": time.time() - start_time,
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


def save_result(result: dict, output_file: Path):
    """Append a result to the JSONL output file."""
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(result) + '\n')


def load_checkpoint(checkpoint_file: Path) -> dict:
    """Load checkpoint state."""
    if checkpoint_file.exists():
        with open(checkpoint_file, 'r') as f:
            return json.load(f)
    return {"completed": 0, "successful": 0, "failed": 0}


def save_checkpoint(checkpoint_file: Path, state: dict):
    """Save checkpoint state."""
    with open(checkpoint_file, 'w') as f:
        json.dump(state, f, indent=2)


def print_progress(completed: int, total: int, successful: int, failed: int, 
                  avg_time: float, start_time: float):
    """Print progress bar and stats."""
    elapsed = time.time() - start_time
    if completed > 0:
        eta_seconds = (elapsed / completed) * (total - completed)
        eta = str(timedelta(seconds=int(eta_seconds)))
    else:
        eta = "calculating..."
    
    pct = (completed / total) * 100 if total > 0 else 0
    bar_length = 40
    filled = int(bar_length * completed / total) if total > 0 else 0
    bar = '█' * filled + '░' * (bar_length - filled)
    
    print(f"\r[{bar}] {completed}/{total} ({pct:.1f}%) | "
          f"✓ {successful} ✗ {failed} | "
          f"Avg: {avg_time:.1f}s | ETA: {eta}  ", end='', flush=True)


def generate_dataset(num_scenarios: int, mode: str = "default", resume: bool = False):
    """
    Main dataset generation function.
    
    Args:
        num_scenarios: Number of scenarios to generate and solve
        mode: Analysis mode (fast, default, pro)
        resume: Whether to resume from checkpoint
    """
    config.ensure_work_dir()
    
    # Setup output directory
    output_dir = config.WORK_DIR / "training_data"
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / "scenarios.jsonl"
    checkpoint_file = output_dir / "checkpoint.json"
    stats_file = output_dir / "DATASET_STATS.txt"
    
    # Load checkpoint if resuming
    state = load_checkpoint(checkpoint_file) if resume else {"completed": 0, "successful": 0, "failed": 0}
    
    completed = state["completed"]
    successful = state["successful"]
    failed = state["failed"]
    
    if not is_solver_available():
        print("⚠️  Solver not available. Dataset generation requires TexasSolver.")
        print("    Place console_solver.exe in solver_bin/ directory.")
        return
    
    print(f"\n🎲 NeuralGTO Dataset Generator")
    print(f"{'='*60}")
    print(f"Mode: {mode}")
    print(f"Target scenarios: {num_scenarios}")
    print(f"Output: {output_file}")
    if resume and completed > 0:
        print(f"Resuming from: {completed} scenarios")
    print()
    
    start_time = time.time()
    solve_times = []
    
    try:
        for i in range(completed, num_scenarios):
            # Generate scenario
            scenario = generate_random_scenario()
            
            # Solve it
            result = solve_scenario(scenario, mode=mode)
            
            if result and result["success"]:
                successful += 1
                solve_times.append(result["solve_time"])
            else:
                failed += 1
            
            # Save result
            if result:
                save_result(result, output_file)
            
            completed += 1
            
            # Update checkpoint
            state = {"completed": completed, "successful": successful, "failed": failed}
            save_checkpoint(checkpoint_file, state)
            
            # Print progress
            avg_time = sum(solve_times) / len(solve_times) if solve_times else 0
            print_progress(completed, num_scenarios, successful, failed, avg_time, start_time)
    
    except KeyboardInterrupt:
        print("\n\n⏸️  Interrupted. Progress saved. Resume with --resume flag.")
        return
    
    print("\n")
    
    # Final statistics
    total_time = time.time() - start_time
    avg_solve_time = sum(solve_times) / len(solve_times) if solve_times else 0
    
    stats = f"""
{'='*60}
NeuralGTO Dataset Generation Complete
{'='*60}

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Mode: {mode}

Scenarios:
  Total:        {num_scenarios}
  Successful:   {successful} ({successful/num_scenarios*100:.1f}%)
  Failed:       {failed} ({failed/num_scenarios*100:.1f}%)

Performance:
  Total time:   {str(timedelta(seconds=int(total_time)))}
  Avg solve:    {avg_solve_time:.2f}s
  Throughput:   {successful/total_time*60:.1f} scenarios/minute

Output:
  Data file:    {output_file}
  Size:         {output_file.stat().st_size / 1024 / 1024:.2f} MB

{'='*60}
"""
    
    print(stats)
    
    # Save stats
    with open(stats_file, 'w') as f:
        f.write(stats)
    
    # Clean up checkpoint
    if checkpoint_file.exists():
        checkpoint_file.unlink()
    
    print(f"✅ Dataset saved to: {output_file}")
    print(f"📊 Stats saved to: {stats_file}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate training dataset for NeuralGTO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 100 scenarios with default settings (2% accuracy, ~2min each = 3-4 hours)
  python -m poker_gpt.dataset_generator --num-scenarios 100

  # Fast mode for quick testing (LLM-only, won't use solver)
  python -m poker_gpt.dataset_generator --num-scenarios 20 --mode fast

  # High quality dataset (0.3% accuracy, ~6min each = 10 hours for 100)
  python -m poker_gpt.dataset_generator --num-scenarios 100 --mode pro

  # Resume interrupted generation
  python -m poker_gpt.dataset_generator --resume
        """
    )
    
    parser.add_argument(
        '--num-scenarios', '-n',
        type=int,
        default=100,
        help='Number of scenarios to generate (default: 100)'
    )
    
    parser.add_argument(
        '--mode', '-m',
        choices=['fast', 'default', 'pro'],
        default='default',
        help='Analysis mode (default: default)'
    )
    
    parser.add_argument(
        '--resume', '-r',
        action='store_true',
        help='Resume from checkpoint'
    )
    
    args = parser.parse_args()
    
    if args.mode == 'fast':
        print("⚠️  Warning: 'fast' mode skips the solver. This will not generate useful training data.")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            return
    
    generate_dataset(args.num_scenarios, args.mode, args.resume)


if __name__ == "__main__":
    main()
