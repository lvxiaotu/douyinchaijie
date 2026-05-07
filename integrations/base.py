from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntegrationManifest:
    id: str
    name: str
    description: str
    repo_url: str | None = None
    tags: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)


class IntegrationAdapter(ABC):
    """Base class for wrapping GitHub projects or local scripts."""

    manifest: IntegrationManifest

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """Return validation errors. Empty list means the config is usable."""

    @abstractmethod
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Start or execute the integration and return a normalized result."""
