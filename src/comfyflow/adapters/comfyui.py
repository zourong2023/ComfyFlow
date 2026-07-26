"""
ComfyUIAdapter — Backend adapter for the ComfyUI /prompt API.

Wraps ComfyUIClient into the BackendAdapter interface.
"""

from __future__ import annotations

from typing import Any

from ..client import ComfyUIClient
from .base import BackendAdapter


class ComfyUIAdapter(BackendAdapter):
    """Adapter wrapping ComfyUIClient for use in multi-backend systems."""

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        url = self.config.get("url", "")
        self.client = ComfyUIClient(url=url)

    def generate(
        self,
        prompt: str,
        mode: str = "txt2img",
        **kwargs: Any,
    ) -> dict[str, Any]:
        from ..pipeline import Pipeline

        pipe = Pipeline(url=self.client.base_url)
        prefix = pipe.encode(prompt, kwargs.get("negative_prompt", ""))
        images = pipe.generate(prefix=prefix, output_prefix="adapter", count=1)
        return {"status": "success", "mode": mode, "outputs": images}

    def check_available(self) -> bool:
        return self.client.check_available()

    def get_models(self) -> list[str]:
        return ["qwen_image", "sdxl"]
