"""Analyzer domain model — ported from Go model/analyzer.go."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Analyzer(BaseModel):
    """Represents a Security Onion analyzer."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    path: str = ""

    def get_module(self) -> str:
        return f"{self.id}.{self.id}"

    def get_requirements_path(self) -> str:
        return f"{self.path}/requirements.txt"

    def get_site_packages_path(self) -> str:
        return f"{self.path}/site-packages"

    def get_source_packages_path(self) -> str:
        return f"{self.path}/source-packages"


def new_analyzer(id: str, path: str) -> Analyzer:
    return Analyzer(id=id, path=path)
