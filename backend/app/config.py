"""Typed settings loaded from the environment / .env file.

Reading configuration in exactly one place means no module has to know where a
value came from, and a missing or malformed setting fails loudly at startup
rather than deep inside a request.

See ``.env.example`` for the documented list of variables.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM provider ---
    llm_provider: str = Field(default="mock", description="'gemini' or 'mock'")
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    # --- Server ---
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Limits ---
    max_labs_per_request: int = 200

    # --- Assistant (retrieval-augmented help widget) ---
    # Separate from the classification pipeline on purpose: the assistant is an
    # extra, and must never be able to affect how results are explained.
    assistant_enabled: bool = True
    ollama_base_url: str = "http://localhost:11434"
    # An instruct model, not a reasoning one. qwen3:4b took 58-83s per answer
    # on CPU and narrated its own thinking into the reply ("Looking at section
    # [1]..."); qwen2.5:3b answers the same questions in 6-12s, cleanly.
    ollama_chat_model: str = "qwen2.5:3b"
    ollama_embed_model: str = "nomic-embed-text"
    # How many chunks of context to put in front of the model. Three rather
    # than five: prompt length is what costs time on CPU, and the answer is
    # almost always in the top two matches anyway.
    assistant_top_k: int = 3
    # Below this cosine similarity a chunk is noise, not context.
    assistant_min_score: float = 0.35

    @field_validator("llm_provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in {"gemini", "mock"}:
            raise ValueError(
                f"LLM_PROVIDER must be 'gemini' or 'mock', got {value!r}"
            )
        return provider

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list, from the comma-separated env value."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def mcp_server_command(self) -> list[str]:
        """Command the MCP client spawns to start the tool server.

        Uses the interpreter running this process, so the subprocess inherits
        the same virtual environment.
        """
        return [sys.executable, "-m", "mcp_server.server"]

    @property
    def mcp_server_cwd(self) -> str:
        """Working directory for the MCP subprocess (the backend package root)."""
        return str(BACKEND_DIR)


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance.

    Cached so the .env file is read once per process, and so FastAPI can use
    this directly as a dependency.
    """
    return Settings()
