"""
ComfyUIClient — Generic HTTP client for the ComfyUI /prompt API.

Usage:
    client = ComfyUIClient(url="http://localhost:8188")
    prompt_id = client.submit_workflow(workflow_dict)
    result = client.wait_for_result(prompt_id, timeout=300)
    saved = client.download_outputs(result, "output/")
"""

from __future__ import annotations

import json
import logging
import os
import time
from base64 import b64encode
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


class ComfyUIClient:
    """Thin wrapper around the ComfyUI /prompt API."""

    def __init__(
        self,
        url: str | None = None,
        auth_user: str | None = None,
        auth_pass: str | None = None,
    ) -> None:
        self.base_url = (
            url
            or os.environ.get("COMFYUI_URL")
            or os.environ.get("COMFYUI_BASE_URL")
            or "http://localhost:8188"
        )
        self.auth_user = auth_user or os.environ.get("COMFYUI_AUTH_USER", "")
        self.auth_pass = auth_pass or os.environ.get("COMFYUI_AUTH_PASS", "")

    # ── public API ──────────────────────────────────────────────

    def submit_workflow(self, workflow: dict) -> str:
        """POST a prompt to ComfyUI, return prompt_id."""
        payload = {"prompt": workflow}
        data = self._request("POST", "/prompt", payload)
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI returned no prompt_id: {data}")
        logger.info("Submitted prompt_id=%s", prompt_id)
        return prompt_id

    def wait_for_result(self, prompt_id: str, timeout: int = 600) -> dict:
        """Poll /history until prompt completes, return the output entry."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                history = self._request("GET", "/history")
                if prompt_id in history:
                    entry = history[prompt_id]
                    if entry.get("status", {}).get("completed"):
                        return entry
                time.sleep(3)
            except Exception as e:
                logger.debug("Poll error: %s", e)
                time.sleep(5)
        raise TimeoutError(f"Timed out waiting for {prompt_id} after {timeout}s")

    def download_outputs(self, prompt_result: dict, output_dir: str) -> dict[str, str]:
        """Download generated images from ComfyUI /view endpoint."""
        outputs = prompt_result.get("outputs", {})
        saved: dict[str, str] = {}
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        for node_id, node_output in outputs.items():
            for img_info in node_output.get("images", []):
                filename = img_info.get("filename", "")
                subfolder = img_info.get("subfolder", "")
                params = f"filename={filename}"
                if subfolder:
                    params += f"&subfolder={subfolder}"
                img_url = f"{self.base_url}/view?{params}"
                dest = out_path / filename
                self._download(img_url, str(dest))
                saved[str(dest)] = img_url
                logger.info("Downloaded: %s", dest)

        return saved

    def check_available(self) -> bool:
        """Check if ComfyUI server is reachable."""
        try:
            self._request("GET", "/system_stats")
            return True
        except Exception:
            return False

    def get_system_stats(self) -> dict:
        """Return full ComfyUI system stats (version, devices, etc.)."""
        try:
            return self._request("GET", "/system_stats")
        except Exception as e:
            return {"error": str(e)}

    # ── internal ────────────────────────────────────────────────

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.auth_user and self.auth_pass:
            creds = b64encode(f"{self.auth_user}:{self.auth_pass}".encode()).decode()
            h["Authorization"] = f"Basic {creds}"
        return h

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base_url.rstrip('/')}{path}"
        resp = requests.request(method, url, json=body, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _download(self, url: str, dest: str) -> None:
        headers = {}
        auth = self._headers().get("Authorization", "")
        if auth:
            headers["Authorization"] = auth
        resp = requests.get(url, headers=headers, stream=True, timeout=60)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
