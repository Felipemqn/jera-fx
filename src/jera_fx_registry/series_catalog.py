from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    source_key: str
    provider: str
    base_url: str
    official: bool
    source_type: str | None = None
    source_mode: str | None = None
    automation_mode: str | None = None
    production_ingestion_approved: bool | None = None
    required_configuration: list[str] = Field(default_factory=list)
    release_metadata_behavior: str
    notes: str
    connection: dict[str, Any] = Field(default_factory=dict)


class SeriesConfig(BaseModel):
    series_key: str
    source_key: str
    source_code: str
    provider: str
    frequency: str
    units: str
    release_metadata_behavior: str
    transformation_rules: dict[str, Any] = Field(default_factory=dict)
    display_metadata: dict[str, Any] = Field(default_factory=dict)
    canonical_scale_policy: dict[str, Any] = Field(default_factory=dict)
    is_placeholder: bool = False

    def definition_hash(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class TacticalDriverConfig(BaseModel):
    driver_key: str
    label: str
    category: str
    required_for_signal: bool = True
    series_key: str | None = None
    source_key: str | None = None
    missing_reason: str | None = None
    source_type: str | None = None
    source_mode: str | None = None
    automation_mode: str | None = None
    production_ingestion_approved: bool | None = None
    required_configuration: list[str] = Field(default_factory=list)
    notes: str | None = None


class TacticalSignalConfig(BaseModel):
    required_drivers: list[TacticalDriverConfig] = Field(default_factory=list)


class SeriesCatalog(BaseModel):
    sources: list[SourceConfig]
    series: list[SeriesConfig]
    tactical_signal: TacticalSignalConfig = Field(default_factory=TacticalSignalConfig)

    def source_map(self) -> dict[str, SourceConfig]:
        return {item.source_key: item for item in self.sources}

    def series_map(self) -> dict[str, SeriesConfig]:
        return {item.series_key: item for item in self.series}

    def get_source(self, source_key: str) -> SourceConfig:
        return self.source_map()[source_key]

    def get_series(self, series_key: str) -> SeriesConfig:
        return self.series_map()[series_key]

    def tactical_driver_map(self) -> dict[str, TacticalDriverConfig]:
        return {item.driver_key: item for item in self.tactical_signal.required_drivers}


def load_series_catalog(path: Path | str) -> SeriesCatalog:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    return SeriesCatalog.model_validate(payload)
