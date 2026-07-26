"""ComfyFlow — ComfyUI Conditioning Cache Pipeline + Web Panel."""

from __future__ import annotations

import json
import logging
import os

import requests

from .template import WorkflowTemplate, PlaceholderTemplate
from .client import ComfyUIClient
from .pipeline import Pipeline
from .agent import PromptAgent

__version__ = "0.1.0"
# Note: adapters intentionally excluded from top-level import to keep the API clean.
# Use: from comfyflow.adapters import ComfyUIAdapter
__all__ = ["WorkflowTemplate", "PlaceholderTemplate", "ComfyUIClient", "Pipeline", "PromptAgent", "_llm_chat"]

logger = logging.getLogger(__name__)


def _llm_chat(messages: list[dict]) -> str:
    """Default LLM call — reads env config, OpenAI-compatible endpoint."""
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL") or os.environ.get("API_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("LLM_MODEL") or os.environ.get("API_MODEL", "gpt-4o-mini")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("LLM call failed: %s — returning raw input", e)
        return messages[-1]["content"] if messages else ""

