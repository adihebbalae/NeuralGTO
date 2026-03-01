# Contributing to NeuralGTO

Thanks for your interest in contributing! NeuralGTO is an open-source neuro-symbolic poker study tool.

## Local Development

```bash
# 1. Clone and set up
git clone https://github.com/adihebbalae/NeuralGTO.git
cd NeuralGTO
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env → set GEMINI_API_KEY (get one at https://aistudio.google.com/apikey)

# 3. Run tests (must pass before submitting)
python -m pytest poker_gpt/tests/ -v -k "not test_full_pipeline_with_api"

# 4. Run the app
streamlit run poker_gpt/web_app.py    # Web UI
python -m poker_gpt.main              # CLI
```

## Code Style

- **Python 3.10+** with type hints on all function signatures
- **Docstrings**: one-line summary + `Args:`, `Returns:`, `Raises:` sections
- **Imports**: stdlib → third-party → local `poker_gpt.*`, separated by blank lines
- **Config**: all paths, env vars, and settings in `config.py` — never hardcode
- **System prompts**: in `poker_gpt/prompts/*.txt` — never inline in Python

## Module Boundaries

Each module has a specific responsibility. Don't blur them:

| Module | Owns | Never does |
|--------|------|------------|
| `config.py` | Paths, env vars, presets | Business logic |
| `poker_types.py` | Data structures only | Any logic |
| `nl_parser.py` | Gemini parse call | Advice, I/O |
| `solver_input.py` | Scenario → solver txt | API calls |
| `solver_runner.py` | Subprocess exec only | Parsing, advice |
| `strategy_extractor.py` | JSON tree navigation | API calls |
| `nl_advisor.py` | Gemini advice call | Parsing |
| `web_app.py` | Streamlit UI only | Business logic |

## Error Handling

- `solver_runner.run_solver()` → returns `None`, never raises
- `nl_parser.parse_scenario()` → raises `ValueError` on bad JSON
- `strategy_extractor.*` → raises `ValueError`/`KeyError` on bad tree
- **Golden rule**: users must never see a Python traceback. Always degrade to LLM-only mode.

## Testing

- Write at least one test for every new feature
- Tests go in `poker_gpt/tests/`
- Offline tests (no API key needed) run by default
- Mark API-dependent tests with `@pytest.mark.integration`
- Run: `python -m pytest poker_gpt/tests/ -v -k "not test_full_pipeline_with_api"`

## Security

- **Never** hardcode API keys, tokens, or passwords
- **Never** use `eval()`, `exec()`, or `shell=True`
- **Always** sanitize user input before passing to external systems
- **Always** validate and bound numeric inputs
- See `.github/instructions/security.instructions.md` for the full security policy

## Submitting Changes

1. Fork the repo and create a feature branch
2. Make your changes with tests
3. Ensure all 425+ tests pass
4. Submit a pull request with:
   - What the change does
   - Why it's needed
   - Test coverage for the change

## Reporting Issues

When filing an issue, include:
- The poker hand/query you used
- Expected vs actual output
- Error message (if any)
- Analysis mode used (fast/default/pro)
