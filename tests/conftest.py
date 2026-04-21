"""Global test guards shared across the full test suite."""

import importlib.util
import os

pytest_plugins = ["pytest_playwright"] if importlib.util.find_spec("pytest_playwright") else []

# Prevent local `.env` loading from re-enabling external tracing during tests.
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_API_KEY"] = ""
os.environ["LANGSMITH_API_KEY"] = ""
os.environ["LANGSMITH_ENDPOINT"] = ""
