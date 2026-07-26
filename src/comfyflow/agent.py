"""
PromptAgent — Generic narrative-to-prompt LLM bridge.

Reads prompt templates from YAML files (no hardcoded worldview content).
Supports both Qwen-Image (Chinese NL) and SDXL (English tags) formats.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class PromptAgent:
    """Generate T2I prompts from text descriptions using an LLM.

    Templates are loaded from config/prompt_templates.yaml.
    Built-in templates are used as fallback if no file exists.
    """

    def __init__(self, template_path: str | Path | None = None) -> None:
        templates: dict[str, Any] = {}
        if template_path:
            tp = Path(template_path)
            if tp.exists():
                with open(tp, encoding="utf-8") as f:
                    templates = yaml.safe_load(f) or {}
            else:
                logger.warning("Template file not found: %s", tp)

        # Fallback to built-in templates
        if not templates.get("qwen"):
            templates.setdefault("qwen", {
                "system": "你是文生图模型的 prompt 工程师。根据用户描述生成中文自然语言 prompt。只输出 prompt，不要解释。",
                "user_template": "生成一段文生图用的中文 prompt，要求包含镜头、主体、光影、色彩。描述：{user_input}",
            })
        if not templates.get("sdxl"):
            templates.setdefault("sdxl", {
                "system": "You are an SDXL prompt engineer. Output comma-separated English tags only. No explanations.",
                "user_template": "Generate an SDXL prompt for: {user_input}",
            })

        self.templates = templates

    def generate_qwen_prompt(self, user_input: str) -> str:
        """Generate a Chinese natural language prompt (Qwen-Image style)."""
        tpl = self.templates.get("qwen", {})
        messages = [
            {"role": "system", "content": tpl.get("system", "")},
            {"role": "user", "content": tpl.get("user_template", "{user_input}").format(user_input=user_input)},
        ]
        return self._call_llm(messages)

    def generate_sdxl_prompt(self, user_input: str) -> str:
        """Generate an SDXL-style comma-separated English tag prompt."""
        tpl = self.templates.get("sdxl", {})
        messages = [
            {"role": "system", "content": tpl.get("system", "")},
            {"role": "user", "content": tpl.get("user_template", "{user_input}").format(user_input=user_input)},
        ]
        return self._call_llm(messages)

    def extract_character(self, text: str) -> dict[str, str]:
        """Extract character visual attributes as JSON.

        Uses a built-in system prompt (no worldview content).
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract the main character's visual attributes from the text. "
                    "Return a JSON object with keys: name, appearance, clothing, pose, expression, environment. "
                    "Only output JSON."
                ),
            },
            {"role": "user", "content": f"Extract character from:\n{text}"},
        ]
        raw = self._call_llm(messages)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Character extraction returned non-JSON: %s", raw[:100])
            return {"name": "", "appearance": raw[:300], "clothing": "", "pose": "", "expression": "", "environment": ""}

    def prompt_for_model(self, user_input: str, model_type: str = "qwen") -> dict[str, Any]:
        """Generate a full prompt package for the given model type.

        Returns:
            dict with keys: positive, negative, character (optional)
        """
        result: dict[str, Any] = {"model_type": model_type}

        if model_type == "qwen":
            result["positive"] = self.generate_qwen_prompt(user_input)
            result["negative"] = "low quality, bad anatomy, ugly, blurry"
        elif model_type.startswith("sdxl"):
            result["positive"] = self.generate_sdxl_prompt(user_input)
            result["negative"] = "lowres, bad anatomy, extra fingers, worst quality, watermark"
        else:
            result["positive"] = user_input
            result["negative"] = ""

        return result

    def _call_llm(self, messages: list[dict]) -> str:
        """Call the LLM via comfyflow's default chat function."""
        from . import _llm_chat
        return _llm_chat(messages)
