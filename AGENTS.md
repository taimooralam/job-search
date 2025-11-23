# Repository Guidelines

## Development Setup
- Python environment: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Run all tests: `python -m pytest`
- Run specific layer: `pytest -k "layer2"` or specific test: `python scripts/test_layer2.py`
- Run workflow: `python -m scripts.run_pipeline`

## Coding Style
- Python: PEP 8 with type hints, docstrings on all public functions
- Imports order: stdlib → third-party → local (grouped, alphabetized)
- Classes: PascalCase, functions/variables: snake_case
- Use error handling with specific exceptions and error context
- Separate implementation classes from LangGraph node functions for testability

## Project Structure
- LangGraph workflow in `src/workflow.py`, layer-specific code in `src/layerN/` modules
- Shared utilities in `src/common/`, CLI scripts in `scripts/`
- Test files follow `test_*.py` naming convention

## LLM Integration
- Use retry decorators with exponential backoff for all LLM calls
- Load API keys from environment variables via `config.py`
- Structure prompts as class constants for readability
- Parse and validate LLM responses before returning

## Security & Validation
- Never commit credentials or `.env` files (only `.env.example`)
- Sanitize all external inputs and validate response schemas
- Follow FireCrawl rate limiting guidelines for web scraping
- Redact PII and sensitive data before logging