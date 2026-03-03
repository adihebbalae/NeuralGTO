"""
solver_input.py — Step 2: ScenarioData → TexasSolver Input File.

Converts the parsed poker scenario into a command file that the 
TexasSolver console binary can process.

Created: 2026-02-06

DOCUMENTATION:
- Input: ScenarioData from nl_parser.py
- Output: A .txt file with solver commands (one per line)
- The file is written to config.SOLVER_INPUT_FILE
- Command format matches TexasSolver's CommandLineTool.processCommand()
"""

from pathlib import Path

from poker_gpt.poker_types import ScenarioData
from poker_gpt import config


def generate_solver_input(
    scenario: ScenarioData,
    output_path: Path = None,
    accuracy: float = None,
    max_iterations: int = None,
    dump_rounds: int = None,
) -> Path:
    """
    Generate a TexasSolver input command file from a ScenarioData object.
    
    Args:
        scenario: The parsed poker scenario.
        output_path: Where to write the file. Defaults to config.SOLVER_INPUT_FILE.
        accuracy: Override solver accuracy (% of pot). None = use config default.
        max_iterations: Override max iterations. None = use config default.
        dump_rounds: Override dump rounds. None = use config default.
        
    Returns:
        Path to the generated input file.
    """
    if output_path is None:
        output_path = config.SOLVER_INPUT_FILE
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    commands = _build_commands(
        scenario,
        accuracy=accuracy,
        max_iterations=max_iterations,
        dump_rounds=dump_rounds,
    )
    
    with open(output_path, "w", encoding="utf-8") as f:
        for cmd in commands:
            f.write(cmd + "\n")
    
    if config.DEBUG:
        print(f"[SOLVER_INPUT] Generated input file: {output_path}")
        print(f"[SOLVER_INPUT] Commands:")
        for cmd in commands:
            print(f"  {cmd}")
    
    return output_path


def _build_commands(
    scenario: ScenarioData,
    accuracy: float = None,
    max_iterations: int = None,
    dump_rounds: int = None,
) -> list[str]:
    """
    Build the list of TexasSolver commands for the given scenario.
    
    Args:
        scenario: The parsed poker scenario.
        accuracy: Override solver accuracy. None = use config default.
        max_iterations: Override max iterations. None = use config default.
        dump_rounds: Override dump rounds. None = use config default.
    
    The solver expects:
    1. set_pot, set_effective_stack, set_board  (game state)
    2. set_range_oop, set_range_ip              (player ranges)
    3. set_bet_sizes for each player/street/type (tree structure)
    4. set_allin_threshold, build_tree           (tree building)
    5. Solver config: threads, accuracy, etc.
    6. start_solve, dump_result                  (execution)
    """
    # Resolve overrides vs config defaults
    _accuracy = accuracy if accuracy is not None else config.SOLVER_ACCURACY
    _max_iterations = max_iterations if max_iterations is not None else config.SOLVER_MAX_ITERATIONS
    _dump_rounds = dump_rounds if dump_rounds is not None else config.SOLVER_DUMP_ROUNDS
    commands = []
    
    # ── Game State ──
    pot = scenario.pot_size_bb
    eff_stack = scenario.effective_stack_bb
    
    commands.append(f"set_pot {pot:.0f}")
    commands.append(f"set_effective_stack {eff_stack:.0f}")
    commands.append(f"set_board {scenario.board}")
    
    # ── Player Ranges ──
    # OOP = player who acts first postflop
    # IP = player who acts last postflop
    commands.append(f"set_range_oop {scenario.oop_range}")
    commands.append(f"set_range_ip {scenario.ip_range}")
    
    # ── Bet Sizes ──
    # We set bet sizes for every street from the current one forward.
    # Using configurable bet sizes (default: 33%, 67%, 100% pot)
    bet_sizes = scenario.bet_sizes_pct
    raise_sizes = scenario.raise_sizes_pct
    
    bet_str = ",".join(str(s) for s in bet_sizes)
    raise_str = ",".join(str(s) for s in raise_sizes)
    
    streets = _get_streets_from(scenario.current_street)
    
    for street in streets:
        # OOP bet sizes
        commands.append(f"set_bet_sizes oop,{street},bet,{bet_str}")
        commands.append(f"set_bet_sizes oop,{street},raise,{raise_str}")
        commands.append(f"set_bet_sizes oop,{street},allin")
        
        # IP bet sizes
        commands.append(f"set_bet_sizes ip,{street},bet,{bet_str}")
        commands.append(f"set_bet_sizes ip,{street},raise,{raise_str}")
        commands.append(f"set_bet_sizes ip,{street},allin")
        
        # Add donk bets for OOP on the river only.
        # Note: TexasSolver's official sample only includes river donk.
        # Adding turn donk dramatically inflates the game tree and can
        # cause timeouts or segfaults on v0.2.0 with high SPR spots.
        if street == "river":
            commands.append(f"set_bet_sizes oop,{street},donk,{bet_str}")
    
    # ── Tree Building ──
    commands.append(f"set_allin_threshold {config.SOLVER_ALLIN_THRESHOLD}")
    commands.append("build_tree")
    
    # ── Solver Configuration ──
    commands.append(f"set_thread_num {config.SOLVER_THREAD_NUM}")
    commands.append(f"set_accuracy {_accuracy}")
    commands.append(f"set_max_iteration {_max_iterations}")
    commands.append(f"set_print_interval {config.SOLVER_PRINT_INTERVAL}")
    commands.append(f"set_use_isomorphism {config.SOLVER_USE_ISOMORPHISM}")
    
    # ── Solve and Dump ──
    commands.append("start_solve")
    commands.append(f"set_dump_rounds {_dump_rounds}")
    
    # Output file path — use forward slashes for cross-platform compatibility
    output_file = str(config.SOLVER_OUTPUT_FILE).replace("\\", "/")
    commands.append(f"dump_result {output_file}")
    
    return commands


def _get_streets_from(current_street: str) -> list[str]:
    """
    Get all streets from the current one through river.
    The solver needs bet sizes for the current street and all subsequent streets.
    """
    all_streets = ["flop", "turn", "river"]
    try:
        start_idx = all_streets.index(current_street)
        return all_streets[start_idx:]
    except ValueError:
        return all_streets  # Default to all streets
