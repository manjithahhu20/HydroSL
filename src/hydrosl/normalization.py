from __future__ import annotations

import re
from dataclasses import asdict
from typing import Dict, Iterable, List, Optional, Tuple

from .models import (
    Asset,
    NormalizedDataset,
    Observation,
    ParseIssue,
    ParsedSheet,
    SeasonalReference,
    SourceRecord,
)
from .parsing import parse_number
from .serialization import to_jsonable


ALIAS_GROUPS = {
    "rambakano": {"rambakan oya", "rambaken oya"},
    "rottikulama": {"rottikulama", "rottaikulam"},
    "senanayakasam": {"senanayaka sam", "senanayaka samudraya"},
    "kalugaloya": {"kalugaloya", "kalugal oya"},
    "huruluwewa": {"huruluwewa", "hurulu wewa"},
    "mahakandarawa": {"mahakandarawa", "mahakanadarawa"},
    "yanoya": {"yan oya", "yanoya"},
    "ambewela": {"ambewela", "ambewala"},
    "unnichchi": {"unnichchi", "unnichchai"},
    "vakaneri": {"vakaneri", "vahanery"},
    "lunugamwehera": {"lunugamwehera", "lunugamvehera"},
    "kimbulwanaoya": {"kimbulwanaoya", "kimbulwana oya", "kimbulwana"},
    "mediyawa": {"mediyawa", "madiyawa"},
    "magalla": {"magalla", "magalla wewa"},
    "jayawewa": {"jayawewa", "jaya wewa (palukadawala)"},
    "usgalasiyabalan": {"usgala siyabalan", "usgala siyabalangamuwa"},
    "kantale": {"kantale", "kantalai"},
    "morawewa": {"mora wewa", "morawewa"},
    "viyathikulam": {"viyathikulam", "viyadikulam"},
    "ellewela": {"ellewela", "ellawela wewa"},
    "badagiriya": {"badagiriya", "bandagiriya"},
    "kekanadura": {"kekanadura", "kekanadura wewa"},
    "ambakolawewa": {"ambakolawewa", "abakola wewa"},
    "hakwatunawa": {"hakwatunawa wawa", "hakwatuna oya"},
    "ridiyagama": {"ridiyagama", "ridiyagama (walawa lb)"},
    "sorabora": {"sorabora", "sorabora wewa"},
    "akathimuruppu": {"akathimuruppu", "akathimurippu"},
}


def _name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


ALIAS_TO_ROOT = {
    _name_key(alias): root
    for root, aliases in ALIAS_GROUPS.items()
    for alias in aliases
}


def canonical_asset_key(name: str) -> str:
    raw_key = _name_key(name)
    return ALIAS_TO_ROOT.get(raw_key, raw_key or "unknown")


def _field(record: SourceRecord, *names: str) -> str:
    wanted = {_name_key(name) for name in names}
    for key, value in record.raw_fields.items():
        if _name_key(key) in wanted:
            return str(value or "").strip()
    return ""


def _coordinate(record: SourceRecord, name: str) -> Optional[float]:
    raw = _field(record, name)
    value, _ = parse_number(raw)
    return value


def _asset_type_key(record: SourceRecord) -> Tuple[str, str]:
    return record.asset_type, canonical_asset_key(record.asset_name)


class EntityResolver:
    """Resolve source names into stable HydroSL asset identifiers."""

    def __init__(self) -> None:
        self.assets: Dict[Tuple[str, str], Asset] = {}

    def resolve(self, record: SourceRecord) -> Asset:
        key = _asset_type_key(record)
        asset = self.assets.get(key)
        if asset is None:
            root = key[1]
            asset = Asset(
                asset_id=f"{record.asset_type}:{root}",
                asset_type=record.asset_type,
                canonical_name=record.asset_name.strip(),
            )
            self.assets[key] = asset

        name = record.asset_name.strip()
        if name and name not in asset.aliases:
            asset.aliases.append(name)

        latitude = _coordinate(record, "latitude")
        longitude = _coordinate(record, "longitude")
        if asset.latitude is None and latitude is not None:
            asset.latitude = latitude
        if asset.longitude is None and longitude is not None:
            asset.longitude = longitude

        for attribute, target in (
            ("range", "range_name"),
            ("division", "division"),
            ("devision", "division"),
            ("district", "district"),
        ):
            value = _field(record, attribute)
            if value and getattr(asset, target) is None:
                setattr(asset, target, value)

        source_key = f"{record.sheet_name}:{record.source_row}"
        if source_key not in asset.source_keys:
            asset.source_keys.append(source_key)
        return asset


def _record_json(record: SourceRecord, asset: Asset) -> Dict[str, object]:
    return {
        "asset_id": asset.asset_id,
        "asset_type": asset.asset_type,
        "asset_name": record.asset_name,
        "sheet_name": record.sheet_name,
        "gid": record.gid,
        "section": record.section,
        "source_row": record.source_row,
        "observed_date": record.observed_date,
        "report_date": record.report_date,
        "season": record.season,
        "raw_fields": record.raw_fields,
        "attributes": record.attributes,
        "metrics": record.metrics,
        "seasonal_references": record.seasonal_references,
    }


def normalize(parsed_sheets: Iterable[ParsedSheet]) -> NormalizedDataset:
    parsed_sheets = list(parsed_sheets)
    resolver = EntityResolver()
    dataset = NormalizedDataset()

    for parsed in parsed_sheets:
        dataset.issues.extend(parsed.issues)
        dataset.summaries.extend(parsed.summaries)
        for record in parsed.records:
            asset = resolver.resolve(record)
            dataset.records.append(_record_json(record, asset))
            for metric in record.metrics.values():
                dataset.observations.append(
                    Observation(
                        asset_id=asset.asset_id,
                        metric_code=metric.code,
                        observed_date=record.observed_date,
                        report_date=record.report_date,
                        value=metric.value,
                        unit=metric.unit,
                        raw_value=metric.raw_value,
                        quality_flag=metric.quality_flag,
                        source_sheet=record.sheet_name,
                        source_gid=record.gid,
                        source_section=record.section,
                        source_row=record.source_row,
                        season=record.season,
                        text_value=metric.text_value,
                        attributes=record.attributes,
                    )
                )
            for period, metric in record.seasonal_references.items():
                dataset.seasonal_references.append(
                    SeasonalReference(
                        asset_id=asset.asset_id,
                        reference_period=period,
                        metric_code=metric.code,
                        value=metric.value,
                        unit=metric.unit,
                        raw_value=metric.raw_value,
                        quality_flag=metric.quality_flag,
                        source_sheet=record.sheet_name,
                        source_gid=record.gid,
                        source_section=record.section,
                        source_row=record.source_row,
                        season=record.season,
                    )
                )

    dataset.assets = sorted(
        resolver.assets.values(), key=lambda asset: (asset.asset_type, asset.canonical_name.lower())
    )
    return dataset
