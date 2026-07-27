"""
Pipeline 鈥?Conditioned generation pipeline (encode 鈫?generate).

Splits generation into two steps:
  1. Encode: CLIPTextEncode 鈫?SaveConditioning (.bin cache)
  2. Generate: LoadConditioning 鈫?KSampler 鈫?SaveImage (no CLIP)

Re-use conditioning across multiple generate calls for the same prompt.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any

from .client import ComfyUIClient
from .template import PlaceholderTemplate, WorkflowTemplate

logger = logging.getLogger(__name__)

_WORKFLOW_DIR = Path(__file__).resolve().parent.parent.parent / "workflows"

# ── 分辨率映射表 ───────────────────────────────────────────
_ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "4:3": (1152, 896),
    "3:2": (1216, 832),
    "16:9": (1344, 768),
    "21:9": (1536, 640),
    "9:16": (768, 1344),
    "2:3": (832, 1216),
    "3:4": (896, 1152),
}


class Pipeline:
    """High-level encode 鈫?generate pipeline.

    Usage:
        pipe = Pipeline(url="http://localhost:8188")
        pipe.encode("1girl, snow", prefix="scene1")
        pipe.generate(prefix="scene1", output_prefix="out", count=3)
    """

    def __init__(
        self,
        url: str | None = None,
        auth_user: str | None = None,
        auth_pass: str | None = None,
        workflow_dir: str | Path | None = None,
    ) -> None:
        self.client = ComfyUIClient(url, auth_user, auth_pass)
        self.wf_dir = Path(workflow_dir) if workflow_dir else _WORKFLOW_DIR

        # Conditioning cache state
        self._cached_prompt_hash: str | None = None
        self._conditioning_cached: bool = False
        self._last_asset_prefix: str = ""

    # 鈹€鈹€ public API 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _resolve_resolution(self, width: int | None, height: int | None, aspect_ratio: str | None) -> list[int]:
        """Return [width, height] from explicit values or aspect_ratio string."""
        if width and height:
            return [width, height]
        if aspect_ratio and aspect_ratio in _ASPECT_RATIOS:
            return list(_ASPECT_RATIOS[aspect_ratio])
        return [1024, 1024]

    def encode(
        self,
        positive_prompt: str,
        negative_prompt: str = "",
        prefix: str = "",
        **extra_vars: Any,
    ) -> str:
        """Step 1: Encode and save conditioning.

        Args:
            positive_prompt: Text prompt for positive conditioning.
            negative_prompt: Text prompt for negative conditioning.
            prefix: Asset prefix for the saved .bin files.

        Returns:
            asset_prefix used (auto-generated if not provided).
        """
        prompt_hash = hashlib.md5(positive_prompt.encode()).hexdigest()
        ts = time.strftime("%Y%m%d_%H%M%S")
        asset_prefix = prefix or f"cf_{ts}_{prompt_hash[:8]}"

        # Build workflow with defaults for unmapped variables
        defaults = {
            "clip_name": "clip_model.safetensors",
            "clip_type": "qwen_image",
            "unet_name": "unet.safetensors",
            "vae_name": "vae.safetensors",
        }
        defaults.update(extra_vars)

        tmpl = self._load_workflow_template("encode")
        wf = tmpl.render(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            conditioning_pos_file=f"{asset_prefix}_positive",
            conditioning_neg_file=f"{asset_prefix}_negative",
            **defaults,
        )

        pid = self.client.submit_workflow(wf)
        self.client.wait_for_result(pid, timeout=120)
        self._conditioning_cached = True
        self._cached_prompt_hash = prompt_hash
        self._last_asset_prefix = asset_prefix
        logger.info("Encode done: prefix=%s, prompt_id=%s", asset_prefix, pid)
        return asset_prefix

    def generate(
        self,
        prefix: str = "",
        output_prefix: str = "comfyflow",
        count: int = 1,
        turbo_mode: bool = False,
        **extra_vars: Any,
    ) -> list[str]:
        """Step 2: Generate image(s) from cached conditioning.

        Args:
            prefix: Asset prefix used in encode().
            output_prefix: Output image filename prefix.
            count: Number of images to generate.
            turbo_mode: Fast (4-step) or quality (50-step) mode.

        Returns:
            List of downloaded image paths.
        """
        asset_prefix = prefix or self._last_asset_prefix
        if not asset_prefix:
            raise RuntimeError("No prefix. Call encode() first or provide a prefix.")

        # Load workflow
        tmpl = self._load_workflow_template("generate")
        pos_file = f"{asset_prefix}_positive_conditionings.bin"
        neg_file = f"{asset_prefix}_negative_conditionings.bin"

        images: list[str] = []
        for i in range(count):
            wf = tmpl.render(
                conditioning_pos_file=pos_file,
                conditioning_neg_file=neg_file,
                output_prefix=output_prefix,
                seed=extra_vars.pop("seed", None) or int(time.time() * 1000) + i,
                **extra_vars,
            )
            pid = self.client.submit_workflow(wf)
            result = self.client.wait_for_result(pid, timeout=300)
            saved = self.client.download_outputs(result, "output")
            images.extend(saved.keys())
            logger.info("Generate #%d: prompt_id=%s, images=%d", i + 1, pid, len(saved))

        return images

    # 鈹€鈹€ helpers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _load_workflow_template(self, stage: str) -> PlaceholderTemplate:
        """Load workflow template (prefer schema-driven, fallback to placeholder)."""
        schema_path = self.wf_dir / ".." / "schemas" / f"{stage}.json"
        wf_path = self.wf_dir / f"{stage}.json"

        if not wf_path.exists():
            raise FileNotFoundError(f"Workflow not found: {wf_path}")

        return PlaceholderTemplate(str(wf_path))
