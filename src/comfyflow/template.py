"""
WorkflowTemplate — Variable injection for ComfyUI workflow JSON files.

Two variants:
  - WorkflowTemplate   (schema-driven, validates types)
  - PlaceholderTemplate (__VAR__ string replace, zero config)
"""

from __future__ import annotations

import json
import re
import random
from pathlib import Path
from typing import Any


class WorkflowTemplate:
    """Schema-driven ComfyUI workflow template.

    Usage:
        tmpl = WorkflowTemplate("workflows/encode.json", schema_path="schemas/encode.json")
        prompt = tmpl.render(positive_prompt="1girl, snow", output_prefix="my_img")
    """

    def __init__(
        self,
        workflow_path: str | Path,
        schema_path: str | Path | None = None,
    ) -> None:
        self.path = Path(workflow_path)
        self.workflow = self._load_json(self.path)
        self.schema: dict[str, Any] = {}
        if schema_path:
            self.schema = self._load_json(Path(schema_path))
            self._validate_schema()

    # ── public API ──────────────────────────────────────────────

    def render(self, **variables: Any) -> dict:
        """Inject variables into the workflow JSON and return a /prompt-ready dict.

        For schema-driven mode: validates types and applies defaults.
        """
        resolved = dict(variables)

        # Apply defaults from schema
        for var_name, meta in self.schema.get("variables", {}).items():
            if var_name not in resolved:
                default = meta.get("default", "")
                if isinstance(default, str):
                    default = self._apply_builtins(default)
                resolved[var_name] = default

        # Type coercion
        for var_name, meta in self.schema.get("variables", {}).items():
            if var_name in resolved:
                resolved[var_name] = self._coerce(resolved[var_name], meta)

        return self._substitute(resolved)

    def list_variables(self) -> list[dict]:
        """Return schema-defined variables for UI auto-generation."""
        return list(self.schema.get("variables", {}).values())

    # ── placeholders ────────────────────────────────────────────

    def _apply_builtins(self, val: str) -> str:
        replacements = {
            "{random_seed}": str(random.randint(1, 2**31)),
        }
        for k, v in replacements.items():
            val = val.replace(k, v)
        return val

    def _substitute(self, variables: dict) -> dict:
        """Walk the workflow JSON and replace __VARIABLE__ occurrences."""
        raw = json.dumps(self.workflow)
        for key, value in variables.items():
            placeholder = f"__{key.upper()}__"
            if isinstance(value, str):
                raw = raw.replace(f'"{placeholder}"', json.dumps(value))
            else:
                raw = raw.replace(f'"{placeholder}"', str(value))
        return json.loads(raw)

    # ── schema / validation ─────────────────────────────────────

    def _validate_schema(self) -> None:
        """Ensure schema variables exist in the workflow JSON."""
        raw = json.dumps(self.workflow)
        for var_name in self.schema.get("variables", {}):
            placeholder = f"__{var_name.upper()}__"
            if placeholder not in raw:
                import warnings
                warnings.warn(
                    f"Schema variable '{var_name}' -> '{placeholder}' not found in workflow"
                )

    def _coerce(self, value: Any, meta: dict) -> Any:
        vtype = meta.get("type", "string")
        try:
            if vtype == "int" and not isinstance(value, int):
                return int(value)
            if vtype == "float" and not isinstance(value, float):
                return float(value)
            if vtype == "bool":
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return bool(value)
        except (ValueError, TypeError):
            pass
        return value

    @staticmethod
    def _load_json(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"Workflow file not found: {path}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)


class PlaceholderTemplate:
    """Zero-config __VAR__ substitution — no schema needed.

    Usage:
        tmpl = PlaceholderTemplate("workflows/generate.json")
        prompt = tmpl.render(positive_prompt="1girl, snow")
    """

    def __init__(self, workflow_path: str | Path) -> None:
        self.path = Path(workflow_path)
        self.workflow = WorkflowTemplate._load_json(self.path)

    def render(self, **variables: Any) -> dict:
        raw = json.dumps(self.workflow)
        for key, value in variables.items():
            placeholder = f"__{key.upper()}__"
            raw = raw.replace(f'"{placeholder}"', json.dumps(value) if isinstance(value, str) else str(value))
        return json.loads(raw)

    def list_variables(self) -> list[dict]:
        """Scan workflow JSON for __UPPER_CASE__ patterns."""
        raw = json.dumps(self.workflow)
        found = set(re.findall(r'"__([A-Z][A-Z_0-9]+)__"', raw))
        return [{"name": v.lower(), "type": "string", "description": f"__{v}__"} for v in sorted(found)]
