"""
BackendAdapter — Abstract base class for image generation backends.

All adapters must implement generate() and check_available().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BackendAdapter(ABC):
    """Abstract interface for image generation backends."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self.timeout = self.config.get("timeout", 300)
        self.name: str = self.config.get("name", self.__class__.__name__)

    @abstractmethod
    def generate(
        self,
        prompt: str,
        mode: str = "txt2img",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate image(s) from prompt."""
        ...

    @abstractmethod
    def check_available(self) -> bool:
        """Check if this backend is reachable."""
        ...

    def get_models(self) -> list[str]:
        return []

    def __repr__(self) -> str:
        return f"{self.name}(available={self.check_available()})"
