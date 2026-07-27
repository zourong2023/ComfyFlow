"""
ComfyFlow Web Panel — Gradio interface for conditioned generation.

Usage:
    python -m comfyflow.panel
    # Opens http://localhost:8500
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import gradio as gr
import yaml
import torch

from dotenv import load_dotenv

from .client import ComfyUIClient
from .pipeline import Pipeline
from .agent import PromptAgent

load_dotenv()

logger = logging.getLogger(__name__)

_CFG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def _check_shader() -> str:
    """Detect available compute device (from Stability AI Toolkit pattern)."""
    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return f"cuda ({torch.cuda.get_device_name(0)})"
    return "cpu"


def _load_models() -> dict[str, Any]:
    path = _CFG_DIR / "models.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _load_templates() -> dict[str, Any]:
    path = _CFG_DIR / "prompt_templates.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class ComfyFlowPanel:
    """Gradio web application with txt2img, img2img, and diagnostics tabs."""

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

            with gr.Tabs():
                # ── Tab 1: Text-to-Image ──
                with gr.TabItem("Text-to-Image"):
                    with gr.Row():
                        with gr.Column(scale=2):
                            prompt = gr.Textbox(
                                label="Prompt", placeholder="Describe the image...",
                                lines=4,
                            )
                            neg_prompt = gr.Textbox(
                                label="Negative Prompt (optional)",
                                placeholder="lowres, bad anatomy...", lines=2,
                            )
                            with gr.Row():
                                model_choice = gr.Dropdown(
                                    choices=list(self.models.get("models", {})),
                                    label="Model Preset", value="",
                                )
                                template_choice = gr.Dropdown(
                                    choices=list(self.templates.keys()),
                                    label="Prompt Template", value="",
                                )
                            with gr.Row():
                                turbo = gr.Checkbox(
                                    label="Turbo Mode (4-step fast)", value=True,
                                )
                                count = gr.Slider(
                                    minimum=1, maximum=10, step=1, value=1,
                                    label="Generate Count",
                                )
                            gen_btn = gr.Button("Generate", variant="primary", size="lg")

                        with gr.Column(scale=3):
                            status = gr.Textbox(label="Status", interactive=False)
                            gallery = gr.Gallery(
                                label="Generated Images", columns=3, rows=2,
                                object_fit="contain", height="auto",
                            )

                    gen_btn.click(
                        fn=self._on_generate,
                        inputs=[prompt, neg_prompt, model_choice, template_choice, turbo, count],
                        outputs=[gallery, status],
                    )

                # ── Tab 2: Image-to-Image (placeholder) ──
                with gr.TabItem("Image-to-Image"):
                    with gr.Row():
                        with gr.Column(scale=2):
                            init_img = gr.Image(
                                type="filepath", label="Initial Image",
                            )
                            img_prompt = gr.Textbox(
                                label="Prompt", placeholder="Describe the edit...",
                                lines=3,
                            )
                            with gr.Row():
                                strength = gr.Slider(
                                    minimum=0, maximum=1, value=0.75,
                                    label="Strength (higher = more change)",
                                )
                            img_gen_btn = gr.Button("Generate from Image",
                                                    variant="primary", size="lg")

                        with gr.Column(scale=3):
                            img_status = gr.Textbox(label="Status", interactive=False)
                            img_output = gr.Image(label="Output")

                    img_gen_btn.click(
                        fn=self._on_img2img,
                        inputs=[init_img, img_prompt, strength],
                        outputs=[img_output, img_status],
                    )

                # ── Tab 3: Diagnostics ──
                with gr.TabItem("Diagnostics"):
                    diag_btn = gr.Button("Run Diagnostics", variant="secondary")
                    diag_output = gr.Textbox(label="Diagnostics Report", lines=10)
                    diag_btn.click(fn=self._on_diagnostics, outputs=[diag_output])

            app.load(fn=self._on_load, outputs=[status])

        return app

    def _on_load(self) -> str:
        available = self.pipeline.client.check_available()
        if available:
            return "ComfyUI connected"
        return "ComfyUI not reachable — set COMFYUI_URL in .env"

    def _on_generate(
        self, prompt_text: str, negative_text: str,
        model_name: str, template_name: str, turbo_mode: bool, gen_count: int,
    ) -> tuple[list[str], str]:
        if not prompt_text.strip():
            return [], "Please enter a prompt."
        try:
            yield [], "Encoding conditioning..."
            if template_name:
                pa = PromptAgent(str(_CFG_DIR / "prompt_templates.yaml"))
                full_prompt = (
                    pa.generate_qwen_prompt(prompt_text)
                    if "qwen" in template_name
                    else pa.generate_sdxl_prompt(prompt_text)
                )
            else:
                full_prompt = prompt_text

            yield [], f"Encoding ({len(full_prompt)} chars)..."
            prefix = self.pipeline.encode(
                positive_prompt=full_prompt, negative_prompt=negative_text,
            )
            yield [], f"Generating {gen_count} image(s)..."
            images = self.pipeline.generate(
                prefix=prefix, output_prefix="comfyflow", count=gen_count,
            )
            yield images, f"Done — {len(images)} image(s) generated"
        except Exception as e:
            logger.exception("Generation failed")
            yield [], f"Error: {e}"

    def _on_img2img(
        self, init_image_path: str | None, prompt_text: str, strength_val: float,
    ) -> tuple[str | None, str]:
        """Image-to-image (placeholder — workflow not yet implemented)."""
        if not init_image_path:
            return None, "Please upload an initial image."
        if not prompt_text.strip():
            return None, "Please enter a prompt."
        return None, (
            "Image-to-image is not yet implemented. "
            "This requires an img2img workflow JSON and ComfyUI support. "
            "Coming in a future release."
        )

    def _on_diagnostics(self) -> str:
        """Run diagnostics and return report."""
        lines = ["=== ComfyFlow Diagnostics ===", ""]

        # 1. Compute device
        lines.append(f"Compute device: {_check_shader()}")

        # 2. Python env
        import sys
        lines.append(f"Python: {sys.version.split()[0]}")

        # 3. Model config
        models = _load_models()
        if models:
            mcount = sum(len(v) for v in models.values() if isinstance(v, list))
            lines.append(f"Models configured: yes")
        else:
            lines.append("Models configured: no (copy models.yaml.example)")

        # 4. ComfyUI connection
        available = self.pipeline.client.check_available()
        lines.append(f"ComfyUI reachable: {available}")
        if available:
            try:
                from .client import _comfyui_request as req
                stats = req("GET", "/system_stats")
                v = stats.get("system", {}).get("comfyui_version", "?")
                lines.append(f"ComfyUI version: {v}")
            except Exception:
                pass

        # 5. Templates
        tmpl = _load_templates()
        lines.append(f"Prompt templates: {len(tmpl)} available")

        # 6. GPU memory (if available)
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            used_gb = (total - free) / 1024**3
            total_gb = total / 1024**3
            lines.append(f"GPU memory: {used_gb:.1f}GB / {total_gb:.1f}GB used")

        return "\n".join(lines)


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
