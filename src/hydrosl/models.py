from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SheetSpec:
    """Published workbook sheet and parser configuration."""

    name: str
    gid: str
    parser: str
    asset_type: Optional[str] = None
    season: Optional[str] = None

    @property
    def csv_url_suffix(self) -> str:
        return f"pub?gid={self.gid}&single=true&output=csv"


@dataclass
class MetricValue:
    code: str
    raw_value: str
    value: Optional[float]
    unit: Optional[str]
    quality_flag: str = "observed"
    text_value: Optional[str] = None
    source_field: Optional[str] = None


@dataclass
class SourceRecord:
    """A source row before entity resolution.

    `raw_fields` intentionally keeps every parsed column. It is the bridge
    between the irregular source sheets and the stable domain model.
    """

    sheet_name: str
    gid: str
    section: str
    source_row: int
    asset_type: str
    asset_name: str
    observed_date: Optional[date]
    report_date: Optional[date]
    season: Optional[str]
    raw_fields: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, MetricValue] = field(default_factory=dict)
    seasonal_references: Dict[str, MetricValue] = field(default_factory=dict)
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass
class Asset:
    asset_id: str
    asset_type: str
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    range_name: Optional[str] = None
    division: Optional[str] = None
    district: Optional[str] = None
    source_keys: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    asset_id: str
    metric_code: str
    observed_date: Optional[date]
    report_date: Optional[date]
    value: Optional[float]
    unit: Optional[str]
    raw_value: str
    quality_flag: str
    source_sheet: str
    source_gid: str
    source_section: str
    source_row: int
    season: Optional[str] = None
    text_value: Optional[str] = None
    source_field: Optional[str] = None
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass
class SeasonalReference:
    asset_id: str
    reference_period: str
    metric_code: str
    value: Optional[float]
    unit: Optional[str]
    raw_value: str
    quality_flag: str
    source_sheet: str
    source_gid: str
    source_section: str
    source_row: int
    season: Optional[str] = None
    observed_date: Optional[date] = None
    report_date: Optional[date] = None
    source_field: Optional[str] = None
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass
class Summary:
    sheet_name: str
    source_gid: str
    section: str
    source_row: int
    scope: Optional[str]
    raw_fields: Dict[str, str] = field(default_factory=dict)
    values: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseIssue:
    sheet_name: str
    source_gid: str
    source_row: Optional[int]
    section: Optional[str]
    field: Optional[str]
    raw_value: Optional[str]
    code: str
    message: str
    severity: str = "warning"


@dataclass
class ParsedSheet:
    spec: SheetSpec
    records: List[SourceRecord] = field(default_factory=list)
    summaries: List[Summary] = field(default_factory=list)
    issues: List[ParseIssue] = field(default_factory=list)
    row_count: int = 0
    report_date: Optional[date] = None


@dataclass
class NormalizedDataset:
    assets: List[Asset] = field(default_factory=list)
    records: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[Observation] = field(default_factory=list)
    seasonal_references: List[SeasonalReference] = field(default_factory=list)
    summaries: List[Summary] = field(default_factory=list)
    issues: List[ParseIssue] = field(default_factory=list)


@dataclass
class SnapshotInfo:
    sheet_name: str
    gid: str
    url: str
    path: str
    sha256: str
    bytes: int
    fetched_at: datetime
    status: str = "ok"
    error: Optional[str] = None
