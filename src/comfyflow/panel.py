"""
ComfyFlow Web Panel — Gradio interface for conditioned generation.

Usage:
    python -m comfyflow.panel
    # Opens http://localhost:8500
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import gradio as gr
import yaml

from .client import ComfyUIClient
from .pipeline import Pipeline
from .agent import PromptAgent

logger = logging.getLogger(__name__)

_CFG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def _load_models() -> dict[str, Any]:
    """Load models.yaml, return empty dict if missing."""
    path = _CFG_DIR / "models.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _load_templates() -> dict[str, Any]:
    """Load prompt_templates.yaml, return empty dict if missing."""
    path = _CFG_DIR / "prompt_templates.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class ComfyFlowPanel:
    """Gradio web application."""

    def __init__(self) -> None:
        self.pipeline = Pipeline()
        self.agent = PromptAgent(str(_CFG_DIR / "prompt_templates.yaml"))
        self.models = _load_models()
        self.templates = _load_templates()

    def build(self) -> gr.Blocks:
        with gr.Blocks(title="ComfyFlow", theme=gr.themes.Soft()) as app:
            gr.Markdown(
                "# ComfyFlow\n"
                "ComfyUI Conditioning Cache Pipeline — Zero CLIP reload."
            )

            with gr.Row():
                with gr.Column(scale=2):
                    prompt = gr.Textbox(
                        label="Prompt",
                        placeholder="Describe the image you want to generate...",
                        lines=4,
                    )
                    neg_prompt = gr.Textbox(
                        label="Negative Prompt (optional)",
                        placeholder="lowres, bad anatomy...",
                        lines=2,
                    )
                    with gr.Row():
                        model_choice = gr.Dropdown(
                            choices=list(self.models.get("models", {})),
                            label="Model Preset",
                            value="",
                        )
                        template_choice = gr.Dropdown(
                            choices=list(self.templates.keys()),
                            label="Prompt Template",
                            value="",
                        )
                    with gr.Row():
                        turbo = gr.Checkbox(
                            label="Turbo Mode (4-step fast)",
                            value=True,
                        )
                        count = gr.Slider(
                            minimum=1, maximum=10, step=1, value=1,
                            label="Generate Count",
                        )
                    gen_btn = gr.Button("Generate", variant="primary", size="lg")

                with gr.Column(scale=3):
                    status = gr.Textbox(label="Status", interactive=False)
                    gallery = gr.Gallery(
                        label="Generated Images",
                        columns=3,
                        rows=2,
                        object_fit="contain",
                        height="auto",
                    )

            # Event handlers
            gen_btn.click(
                fn=self._on_generate,
                inputs=[prompt, neg_prompt, model_choice, template_choice, turbo, count],
                outputs=[gallery, status],
            )

            # Status bar on load
            app.load(fn=self._on_load, outputs=[status])

        return app

    def _on_load(self) -> str:
        """Check ComfyUI connectivity on panel load."""
        available = self.pipeline.client.check_available()
        if available:
            return "✅ ComfyUI connected"
        return "⚠️ ComfyUI not reachable — set COMFYUI_URL in .env"

    def _on_generate(
        self,
        prompt_text: str,
        negative_text: str,
        model_name: str,
        template_name: str,
        turbo_mode: bool,
        gen_count: int,
    ) -> tuple[list[str], str]:
        if not prompt_text.strip():
            return [], "Please enter a prompt."

        try:
            status_msg = "Encoding conditioning..."
            yield [], status_msg

            # 1. Generate prompt via LLM if template is selected
            if template_name:
                pa = PromptAgent(str(_CFG_DIR / "prompt_templates.yaml"))
                if "qwen" in template_name:
                    full_prompt = pa.generate_qwen_prompt(prompt_text)
                else:
                    full_prompt = pa.generate_sdxl_prompt(prompt_text)
            else:
                full_prompt = prompt_text

            # 2. Encode conditioning
            status_msg = f"Encoding ({len(full_prompt)} chars)..."
            yield [], status_msg
            prefix = self.pipeline.encode(
                positive_prompt=full_prompt,
                negative_prompt=negative_text,
            )

            # 3. Generate images
            status_msg = f"Generating {gen_count} image(s)..."
            yield [], status_msg
            images = self.pipeline.generate(
                prefix=prefix,
                output_prefix="comfyflow",
                count=gen_count,
            )

            status_msg = f"✅ Done — {len(images)} image(s) generated"
            yield images, status_msg

        except Exception as e:
            logger.exception("Generation failed")
            yield [], f"❌ Error: {e}"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8500"))

    panel = ComfyFlowPanel()
    app = panel.build()
    app.launch(server_name=host, server_port=port, share=False)


if __name__ == "__main__":
    main()
