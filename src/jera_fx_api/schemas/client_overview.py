from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ScalarValue(BaseModel):
    value: float
    units: str
    scale_policy: str


class DistributionBands(BaseModel):
    percentile_rank: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float


class ReerSeriesOverview(BaseModel):
    series_key: str
    source_code: str
    reference_month_end: date
    native: ScalarValue
    canonical: ScalarValue
    distribution: DistributionBands
    normalization_factor: float


class ReerOverview(BaseModel):
    client_default_scale_policy: str
    broad: ReerSeriesOverview
    narrow: ReerSeriesOverview


class SpotOverview(BaseModel):
    series_key: str
    source_code: str
    observation_date: date
    reference_month_end: date
    value: float
    units: str
    scale_policy: str


class SourceFreshness(BaseModel):
    source_key: str
    latest_observation_date: date
    latest_reference_month_end: date
    latest_ingested_at: datetime


class NormalizationPolicy(BaseModel):
    native_scale_policy: str
    canonical_scale_policy: str
    anchor_year: int
    client_default_scale_policy: str
    prototype_status: str


class LastUpdated(BaseModel):
    snapshot_created_at: datetime
    latest_reer_reference_month_end: date
    latest_ptax_observation_date: date
    sources: list[SourceFreshness]


class ClientOverviewResponse(BaseModel):
    snapshot_type: str
    reference_month_end: date
    spot: SpotOverview
    reer: ReerOverview
    normalization_policy: NormalizationPolicy
    last_updated: LastUpdated


class ReerBandsResponse(BaseModel):
    snapshot_type: str
    reference_month_end: date
    client_default_scale_policy: str
    normalization_policy: NormalizationPolicy
    broad: ReerSeriesOverview
    narrow: ReerSeriesOverview


class SpotFreshnessPoint(BaseModel):
    observation_date: date | None = None
    reference_month_end: date
    value: float
    units: str
    scale_policy: str
    released_at: datetime | None = None
    ingested_at: datetime | None = None


class SpotFreshness(BaseModel):
    series_key: str
    source_code: str
    latest_spot: SpotFreshnessPoint
    latest_monthly_close: SpotFreshnessPoint


class SourceFreshnessEntry(BaseModel):
    source_key: str
    latest_observation_date: date
    latest_reference_month_end: date
    latest_released_at: datetime | None = None
    latest_ingested_at: datetime


class SourceFreshnessResponse(BaseModel):
    snapshot_type: str
    reference_month_end: date
    snapshot_created_at: datetime
    sources: list[SourceFreshnessEntry]
    spot_freshness: SpotFreshness


class SeriesPoint(BaseModel):
    series_key: str
    source_key: str
    source_code: str
    provider: str | None = None
    source_type: str | None = None
    source_mode: str | None = None
    automation_mode: str | None = None
    production_ingestion_approved: bool | None = None
    observation_date: date
    reference_month_end: date
    value: float
    units: str
    scale_policy: str
    released_at: datetime | None = None
    ingested_at: datetime
    target_reference: str | None = None


class MonthlyHistoryPoint(BaseModel):
    reference_month_end: date
    observation_date: date | None = None
    value: float
    units: str
    scale_policy: str


class LatestObservationPoint(BaseModel):
    observation_date: date | None = None
    reference_month_end: date | None = None
    value: float | None = None
    units: str | None = None
    scale_policy: str | None = None
    released_at: datetime | None = None
    ingested_at: datetime | None = None


class PtaxHistorySeries(BaseModel):
    series_key: str
    source_code: str | None = None
    points: list[MonthlyHistoryPoint]
    latest_monthly_close: MonthlyHistoryPoint | None = None
    latest_observation: LatestObservationPoint


class PtaxHistoryResponse(BaseModel):
    snapshot_type: str
    reference_month_end: date
    snapshot_created_at: datetime
    series: list[PtaxHistorySeries]


class ReerInputPoint(BaseModel):
    series_key: str
    source_key: str
    source_code: str
    observation_date: date
    reference_month_end: date
    released_at: datetime | None = None
    ingested_at: datetime
    native: ScalarValue
    canonical: ScalarValue
    normalization_factor: float


class DomesticMacroInputs(BaseModel):
    selic_target_rate: SeriesPoint
    focus_exchange_rate: list[SeriesPoint]
    focus_ipca: list[SeriesPoint]


class MissingDriverDetail(BaseModel):
    driver_key: str
    status: str
    source_key: str | None = None
    provider: str | None = None
    source_type: str | None = None
    source_mode: str | None = None
    automation_mode: str | None = None
    production_ingestion_approved: bool | None = None
    configured_for_runtime: bool | None = None
    required_configuration: list[str] = Field(default_factory=list)
    reason: str
    notes: str | None = None


class MarketInputs(BaseModel):
    broad_usd_index: SeriesPoint | None = None
    commodity_terms_of_trade: SeriesPoint | None = None
    cds_brazil_5y: SeriesPoint | MissingDriverDetail | None = None


class DriverCoverage(BaseModel):
    available_driver_keys: list[str]
    missing_driver_keys: list[str]


class MethodologyMetadata(BaseModel):
    version: str
    status: str
    readiness_snapshot_type: str


class TacticalSignalInputsResponse(BaseModel):
    snapshot_type: str
    reference_month_end: date
    snapshot_created_at: datetime
    client_default_reer_scale_policy: str
    signal_computable: bool
    missing_driver_keys: list[str]
    driver_coverage: DriverCoverage
    methodology: MethodologyMetadata
    spot: SeriesPoint
    ptax_monthly_close: SeriesPoint
    reer: dict[str, ReerInputPoint]
    domestic_macro: DomesticMacroInputs
    market: MarketInputs


class DriverReadiness(BaseModel):
    driver_key: str
    label: str
    category: str
    status: str
    series_key: str | None = None
    source_key: str | None = None
    provider: str | None = None
    source_type: str | None = None
    source_mode: str | None = None
    automation_mode: str | None = None
    production_ingestion_approved: bool | None = None
    configured_for_runtime: bool | None = None
    required_configuration: list[str] = Field(default_factory=list)
    latest_observation_date: date | None = None
    latest_reference_month_end: date | None = None
    reason: str | None = None
    notes: str | None = None


class TacticalSignalReadinessResponse(BaseModel):
    snapshot_type: str
    reference_month_end: date
    snapshot_created_at: datetime
    signal_computable: bool
    available_driver_keys: list[str]
    missing_driver_keys: list[str]
    available_drivers: list[DriverReadiness]
    missing_drivers: list[DriverReadiness]
    missing_driver_policy: str


class DriverHistoryPoint(BaseModel):
    reference_month_end: date
    observation_date: date | None = None
    value: float
    units: str
    scale_policy: str


class TacticalDriverEntry(BaseModel):
    driver_key: str
    label: str
    category: str
    status: str
    required_for_signal: bool
    series_key: str | None = None
    source_key: str | None = None
    provider: str | None = None
    source_type: str | None = None
    source_mode: str | None = None
    automation_mode: str | None = None
    production_ingestion_approved: bool | None = None
    configured_for_runtime: bool | None = None
    required_configuration: list[str] = Field(default_factory=list)
    latest: SeriesPoint | None = None
    latest_monthly_close: SeriesPoint | None = None
    latest_native: ScalarValue | None = None
    latest_canonical: ScalarValue | None = None
    normalization_factor: float | None = None
    latest_observation_date: date | None = None
    latest_reference_month_end: date | None = None
    history_scale_policy: str | None = None
    points: list[DriverHistoryPoint] = Field(default_factory=list)
    reason: str | None = None
    notes: str | None = None


class TacticalDriversResponse(BaseModel):
    snapshot_type: str
    reference_month_end: date
    latest_snapshot_created_at: datetime
    history_snapshot_created_at: datetime
    signal_computable: bool
    missing_driver_keys: list[str]
    drivers: list[TacticalDriverEntry]


class TacticalDriverFreshnessEntry(BaseModel):
    driver_key: str
    label: str
    category: str
    status: str
    required_for_signal: bool
    series_key: str | None = None
    source_key: str | None = None
    provider: str | None = None
    source_type: str | None = None
    source_mode: str | None = None
    automation_mode: str | None = None
    production_ingestion_approved: bool | None = None
    configured_for_runtime: bool | None = None
    required_configuration: list[str] = Field(default_factory=list)
    latest_observation_date: date | None = None
    latest_reference_month_end: date | None = None
    latest_released_at: datetime | None = None
    latest_ingested_at: datetime | None = None
    reason: str | None = None
    notes: str | None = None


class TacticalDriverFreshnessResponse(BaseModel):
    snapshot_type: str
    reference_month_end: date
    snapshot_created_at: datetime
    signal_computable: bool
    missing_driver_keys: list[str]
    drivers: list[TacticalDriverFreshnessEntry]


class TacticalSignalMethodologyMetadata(BaseModel):
    version: str
    status: str
    readiness_snapshot_type: str
    inputs_snapshot_type: str
    freshness_snapshot_type: str
    score_published: bool
    definition: dict | None = None


class DriverAutomationMetadata(BaseModel):
    driver_key: str
    source_key: str | None = None
    source_mode: str | None = None
    automation_mode: str | None = None
    production_ingestion_approved: bool | None = None


class TacticalSignalLastUpdated(BaseModel):
    inputs_snapshot_created_at: datetime
    readiness_snapshot_created_at: datetime
    freshness_snapshot_created_at: datetime


class DriverContribution(BaseModel):
    driver_key: str
    weight: float
    z_score: float
    weighted_contribution: float
    inverted: bool
    value: float
    mean: float
    std: float
    history_points: int


class ScoreCoverage(BaseModel):
    available: list[str] = Field(default_factory=list)
    insufficient: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class TacticalSignalResponse(BaseModel):
    snapshot_type: str
    reference_month_end: date
    snapshot_created_at: datetime
    status: str
    client_default_reer_scale_policy: str
    signal_computable: bool
    source_coverage: DriverCoverage
    methodology: TacticalSignalMethodologyMetadata
    score: float | None = None
    regime: str | None = None
    driver_contributions: list[DriverContribution] = Field(default_factory=list)
    coverage: ScoreCoverage = Field(default_factory=ScoreCoverage)
    degraded_reasons: list[str] = Field(default_factory=list)
    freshness_metadata: list[TacticalDriverFreshnessEntry]
    automation_modes: list[DriverAutomationMetadata]
    last_updated: TacticalSignalLastUpdated
