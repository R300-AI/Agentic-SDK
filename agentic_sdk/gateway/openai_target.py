"""Helpers for validating the configured OpenAI-compatible target."""

from __future__ import annotations


DEFAULT_OPENAI_BASE_URL = "http://localhost:8000/v1"


def uses_placeholder_local_openai(base_url: str) -> bool:
    return (base_url or "").rstrip("/") == DEFAULT_OPENAI_BASE_URL.rstrip("/")