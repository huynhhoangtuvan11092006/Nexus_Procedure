"""
NexusProcure AI - Core Configuration Module.

Loads settings from environment variables and .env file.
Provides centralized paths, model identifiers, and negotiation thresholds.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
# Base directory of the project (d:\MultiAgent)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    # Graceful manual fallback parser for .env if python-dotenv is not yet installed
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val


class Settings:
    """Central configuration class for NexusProcure AI."""

    # Project Information
    PROJECT_NAME: str = "NexusProcure AI"
    VERSION: str = "1.0.0"
    BASE_DIR: Path = BASE_DIR

    # LLM Provider Configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq").lower()

    # 1. Groq Configuration
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")
    GROQ_STRATEGIC_MODEL: str = os.getenv("GROQ_STRATEGIC_MODEL", "openai/gpt-oss-120b")
    GROQ_FAST_MODEL: str = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-120b")
    GROQ_TEMPERATURE_STRATEGIC: float = float(os.getenv("GROQ_TEMPERATURE_STRATEGIC", "0.2"))
    GROQ_TEMPERATURE_FAST: float = float(os.getenv("GROQ_TEMPERATURE_FAST", "0.1"))

    # 2. Google Gemini Configuration
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_TEMPERATURE: float = float(os.getenv("GEMINI_TEMPERATURE", "0.2"))

    # Storage Paths
    SQLITE_DB_PATH: Path = BASE_DIR / os.getenv("SQLITE_DB_PATH", "app/data/procurement.db")
    CHROMA_PERSIST_DIR: Path = BASE_DIR / os.getenv("CHROMA_PERSIST_DIR", "app/data/chroma_db")
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

    # Negotiation Arena Defaults
    MAX_NEGOTIATION_ROUNDS: int = int(os.getenv("MAX_NEGOTIATION_ROUNDS", "4"))
    DEFAULT_CONCESSION_RATE: float = float(os.getenv("DEFAULT_CONCESSION_RATE", "0.03"))

    # Multi-Attribute Utility Weights (Default)
    WEIGHT_COST: float = 0.45
    WEIGHT_DELIVERY: float = 0.35
    WEIGHT_TERMS: float = 0.20

    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure necessary data and storage directories exist."""
        cls.SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        cls.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)


# Global singleton instance
settings = Settings()
settings.ensure_directories()
