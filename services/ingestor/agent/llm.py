"""Anthropic chat model wrapper.

Isolates `langchain_anthropic` behind a project-owned interface — nodes never
import it directly, so swapping providers later touches only this module.
Local import (not top-level): `anthropic`/`langchain-anthropic` are optional
extras (`uv sync --extra ai`) — importing them lazily lets the rest of the
ingestor run fine when the extra isn't installed, matching the existing
`from openai import AsyncOpenAI` pattern in routers/observations.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.ingestor.core.config import settings


if TYPE_CHECKING:
    from langchain_anthropic import ChatAnthropic


def get_chat_model(*, deep: bool = False) -> ChatAnthropic:
    """Return a configured Anthropic chat model.

    Args:
        deep: use `anthropic_model_deep` (root-cause analysis) instead of
            `anthropic_model` (cheap/fast severity classification).
    """
    from langchain_anthropic import ChatAnthropic

    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured — the incident-triage agent "
            "cannot call the LLM."
        )

    model = settings.anthropic_model_deep if deep else settings.anthropic_model
    return ChatAnthropic(
        model_name=model,
        api_key=settings.anthropic_api_key,
        timeout=60.0,
        max_retries=2,
    )
