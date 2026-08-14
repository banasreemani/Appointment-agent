"""Centralized loading of project environment variables."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ENV_FILE = Path(__file__).resolve().parent / ".env"


@lru_cache(maxsize=1)
def load_project_environment() -> None:
    """Load the project-root .env once without overriding process variables."""
    load_dotenv(dotenv_path=PROJECT_ENV_FILE, override=False)


def required_environment_variable(name: str) -> str:
    """Return a required setting after loading the project-root .env file."""
    load_project_environment()
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value
