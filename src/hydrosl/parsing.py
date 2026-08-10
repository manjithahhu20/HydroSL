from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import (
    MetricValue,
    ParseIssue,
    ParsedSheet,
    SheetSpec,
    SourceRecord,
    Summary,
)


MISSING_VALUES = {"", "-", "--", "n/a", "na", "null", "none", "nil"}


def clean_cell(value: object) -> str:
    return str(value or "").replace("\ufeff", "").strip()


def canonical_header(value: object) -> str:
    text = clean_cell(value).lower()
    text = text.replace("%", " pct ").replace("#", " number ")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def unique_headers(row: Sequence[str]) -> List[str]:
    headers: List[str] = []
    counts: Dict[str, int] = {}
    for position, raw in enumerate(row, start=1):
        header = clean_cell(raw) or f"unnamed_{position}"
        counts[header] = counts.get(header, 0) + 1
        if counts[header] > 1:
            header = f"{header}_{counts[header]}"
        headers.append(header)
    return headers


def slug_key(value: object) -> str:
    text = canonical_header(value)
    return text or "unknown"


def parse_number(value: object) -> Tuple[Optional[float], str]:
    """Parse a plain numeric cell without hiding source problems."""
    text = clean_cell(value)
    if text.lower() in MISSING_VALUES:
        return None, "missing"
    if text.lower() in {"#ref!", "#n/a", "#value!", "#div/0!"}:
        return None, "source_error"

    normalized = text.replace(",", "").replace("%", "")
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", normalized):
        return float(normalized), "observed"
    return None, "textual_value"


def parse_date_value(
    value: object,
    *,
    default_year: Optional[int] = None,
    slash_order: str = "mdy",
) -> Optional[date]:
    text = clean_cell(value)
    if not text or text.lower() in MISSING_VALUES:
        return None

    text = re.sub(r"(?i)\bof\b", "", text)
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()

    formats = (
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d-%B-%Y",
        "%d-%B-%y",
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    if default_year is not None:
        for fmt in ("%d-%b", "%d-%B", "%d %b", "%d %B"):
            try:
                parsed = datetime.strptime(f"{text} {default_year}", f"{fmt} %Y")
                return parsed.date()
            except ValueError:
                continue

    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", text):
        first, second, year = (int(part) for part in text.split("/"))
        month, day = (first, second) if slash_order == "mdy" else (second, first)
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def extract_report_date(rows: Sequence[Sequence[str]]) -> Optional[date]:
    """Find the report date from title rows before a table header."""
    candidates: List[str] = []
    for row in rows[:12]:
        candidates.extend(clean_cell(cell) for cell in row if clean_cell(cell))
    joined = " ".join(candidates)

    ordinal = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+of\s+([A-Za-z]+)\s+(\d{4})\b",
        joined,
        flags=re.IGNORECASE,
    )
    if ordinal:
        parsed = parse_date_value(
            f"{ordinal.group(1)} {ordinal.group(2)} {ordinal.group(3)}"
        )
        if parsed:
            return parsed

    full = re.search(
        r"\b(\d{1,2})[- ]([A-Za-z]{3,9})[- ](\d{2,4})\b", joined
    )
    if full:
        parsed = parse_date_value(
            f"{full.group(1)}-{full.group(2)}-{full.group(3)}"
        )
        if parsed:
            return parsed

    return None


def _field(fields: Dict[str, str], *needles: str) -> str:
    for key, value in fields.items():
        normalized = canonical_header(key)
        if all(needle in normalized for needle in needles):
            return clean_cell(value)
    return ""


def _first_field(fields: Dict[str, str], *names: str) -> str:
    normalized_names = {canonical_header(name) for name in names}
    for key, value in fields.items():
        if canonical_header(key) in normalized_names:
            return clean_cell(value)
    return ""


def _metric_definition(field_name: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    key = canonical_header(field_name)

    seasonal = re.search(
        r"(?:effective_storage|es)(?:_acft)?_?(\d{2,4}(?:_\d{2,4})?)",
        key,
    )
    if seasonal:
        period = seasonal.group(1)
        return "effective_storage_acft", "Acft", period

    if key.startswith("fsd"):
        return "fsd_ft", "ft", None
    if "water_depth" in key:
        return "water_depth_ft", "ft", None
    if key == "water_level" or key.startswith("water_level_"):
        return "water_level", None, None
    if "gross_extent" in key:
        return "gross_extent_ac", "Ac", None
    if key.startswith("fsl"):
        return "fsl_mmsl", "mMSL", None
    if "gross_capacity" in key or key.startswith("gross_storage"):
        if "gross_storage" in key and "capacity" not in key:
            return "gross_storage_acft", "Acft", None
        return "gross_capacity_acft", "Acft", None
    if "dead_storage" in key:
        return "dead_storage_acft", "Acft", None
    if "active_storage" in key:
        return "active_storage_acft", "Acft", None
    if "present_storage" in key:
        return "present_storage_acft", "Acft", None
    if "long_term" in key and ("average" in key or "avarage" in key):
        return "long_term_average_acft", "Acft", None
    if "effective_storage" in key and "pct" in key:
        return "effective_storage_pct", "%", None
    if "effective_storage" in key:
        return "effective_storage_acft", "Acft", None
    if "rain" in key:
        return "rainfall_preceding_day_mm", "mm", None
    if key in {"spilling", "spilling_y_n"}:
        return "spilling", None, None
    if "spill_value" in key:
        return "spill_value_acft", "Acft", None
    if "total_sluice" in key or "sluice_issues" in key:
        return "sluice_discharge_cusec", "cusec", None
    if key == "sluice" or key.startswith("sluice_"):
        return "sluice_status", None, None
    if "spilling" in key and ("cusec" in key or "discharge" in key):
        return "spilling_discharge_cusec", "cusec", None
    if "diversion" in key:
        return "diversion_cusec", "cusec", None
    if "other_water_outflow" in key:
        return "other_outflow", None, None
    if key == "ds_impact":
        return "ds_impact", None, None
    return None


def _metric_value(field_name: str, raw_value: str) -> Optional[MetricValue]:
    definition = _metric_definition(field_name)
    if definition is None:
        return None
    code, unit, _ = definition
    raw_text = clean_cell(raw_value)
    if code in {"spilling", "ds_impact", "sluice_status"}:
        if raw_text.lower() in MISSING_VALUES:
            return MetricValue(
                code=code,
                raw_value=raw_text,
                value=None,
                unit=unit,
                quality_flag="missing",
            )
        if raw_text.lower() in {"#ref!", "#n/a", "#value!", "#div/0!"}:
            return MetricValue(
                code=code,
                raw_value=raw_text,
                value=None,
                unit=unit,
                quality_flag="source_error",
            )
        return MetricValue(
            code=code,
            raw_value=raw_text,
            value=None,
            unit=unit,
            quality_flag="observed_text",
            text_value=raw_text,
        )

    value, quality = parse_number(raw_value)
    text_value = None
    if quality == "textual_value":
        text_value = clean_cell(raw_value)
    return MetricValue(
        code=code,
        raw_value=clean_cell(raw_value),
        value=value,
        unit=unit,
        quality_flag=quality,
        text_value=text_value,
    )


def _fields_from_row(headers: Sequence[str], row: Sequence[str]) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for index, header in enumerate(headers):
        fields[header] = clean_cell(row[index]) if index < len(row) else ""
    return fields


def _name_from_fields(fields: Dict[str, str]) -> str:
    for key in fields:
        normalized = canonical_header(key)
        if normalized in {"reservoir", "reservoir_name", "anicut", "mediaum_tank", "medium_tank"}:
            return clean_cell(fields[key])
    return ""


def _date_from_fields(
    fields: Dict[str, str], report_date: Optional[date], *, slash_order: str = "mdy"
) -> Optional[date]:
    for key, value in fields.items():
        normalized = canonical_header(key)
        if normalized in {"date", "updated_date", "update_date"}:
            default_year = report_date.year if report_date else None
            return parse_date_value(value, default_year=default_year, slash_order=slash_order)
    return None


def _record_from_row(
    spec: SheetSpec,
    *,
    section: str,
    source_row: int,
    headers: Sequence[str],
    row: Sequence[str],
    asset_type: str,
    report_date: Optional[date],
    season: Optional[str] = None,
    slash_order: str = "mdy",
) -> Tuple[Optional[SourceRecord], List[ParseIssue]]:
    fields = _fields_from_row(headers, row)
    asset_name = _name_from_fields(fields)
    if not asset_name:
        return None, []

    observed_date = _date_from_fields(fields, report_date, slash_order=slash_order)
    metrics: Dict[str, MetricValue] = {}
    seasonal_references: Dict[str, MetricValue] = {}
    issues: List[ParseIssue] = []
    for field_name, raw_value in fields.items():
        metric = _metric_value(field_name, raw_value)
        if metric is None:
            continue
        definition = _metric_definition(field_name)
        if definition and definition[2] is not None:
            seasonal_references[definition[2]] = metric
        else:
            metrics[metric.code] = metric
        if metric.quality_flag in {"source_error", "textual_value"}:
            issues.append(
                ParseIssue(
                    sheet_name=spec.name,
                    source_gid=spec.gid,
                    source_row=source_row,
                    section=section,
                    field=field_name,
                    raw_value=metric.raw_value,
                    code=metric.quality_flag,
                    message=f"Could not parse {field_name!r} as a plain numeric value",
                )
            )

    attributes: Dict[str, str] = {}
    for field_name, raw_value in fields.items():
        key = canonical_header(field_name)
        if any(token in key for token in ("range", "division", "devision", "district", "latitude", "longitude", "remarks")):
            attributes[key] = raw_value

    return (
        SourceRecord(
            sheet_name=spec.name,
            gid=spec.gid,
            section=section,
            source_row=source_row,
            asset_type=asset_type,
            asset_name=asset_name,
            observed_date=observed_date,
            report_date=report_date,
            season=season,
            raw_fields=fields,
            metrics=metrics,
            seasonal_references=seasonal_references,
            attributes=attributes,
        ),
        issues,
    )


def _header_index(rows: Sequence[Sequence[str]], required: Iterable[str]) -> Optional[int]:
    required = tuple(required)
    for index, row in enumerate(rows):
        values = [canonical_header(cell) for cell in row]
        if all(any(requirement in value for value in values) for requirement in required):
            return index
    return None


def _is_blank(row: Sequence[str]) -> bool:
    return not any(clean_cell(cell) for cell in row)


def _summary_header_index(rows: Sequence[Sequence[str]], start: int) -> Optional[int]:
    for index in range(start, len(rows)):
        values = {canonical_header(cell) for cell in rows[index]}
        if "range" in values and any("storage" in value for value in values):
            return index
    return None


def _parse_summaries(
    spec: SheetSpec, rows: Sequence[Sequence[str]], start: int
) -> List[Summary]:
    header_index = _summary_header_index(rows, start)
    if header_index is None:
        return []
    headers = unique_headers(rows[header_index])
    summaries: List[Summary] = []
    for index in range(header_index + 1, len(rows)):
        row = rows[index]
        if _is_blank(row):
            if summaries:
                break
            continue
        fields = _fields_from_row(headers, row)
        scope = _field(fields, "range") or _field(fields, "total")
        if not scope and not any(fields.values()):
            continue
        if scope or any(parse_number(value)[0] is not None for value in fields.values()):
            summaries.append(
                Summary(
                    sheet_name=spec.name,
                    source_gid=spec.gid,
                    section="regional_summary",
                    source_row=index + 1,
                    scope=scope or None,
                    raw_fields=fields,
                )
            )
    return summaries


def _parse_tabular(
    spec: SheetSpec,
    rows: Sequence[Sequence[str]],
    *,
    asset_type: str,
    section: str,
    report_date: Optional[date],
    required: Iterable[str] = ("reservoir",),
    season: Optional[str] = None,
    slash_order: str = "mdy",
) -> ParsedSheet:
    parsed = ParsedSheet(spec=spec, row_count=len(rows), report_date=report_date)
    header_index = _header_index(rows, required)
    if header_index is None:
        parsed.issues.append(
            ParseIssue(
                sheet_name=spec.name,
                source_gid=spec.gid,
                source_row=None,
                section=section,
                field=None,
                raw_value=None,
                code="header_not_found",
                message=f"Could not find a table header containing {tuple(required)!r}",
                severity="error",
            )
        )
        return parsed

    headers = unique_headers(rows[header_index])
    for index in range(header_index + 1, len(rows)):
        row = rows[index]
        if _is_blank(row):
            if parsed.records:
                break
            continue
        joined = " ".join(canonical_header(cell) for cell in row)
        if "summary" in joined or ("range" in joined and "storage" in joined):
            break
        record, issues = _record_from_row(
            spec,
            section=section,
            source_row=index + 1,
            headers=headers,
            row=row,
            asset_type=asset_type,
            report_date=report_date,
            season=season,
            slash_order=slash_order,
        )
        if record is not None:
            parsed.records.append(record)
            parsed.issues.extend(issues)
    parsed.summaries.extend(_parse_summaries(spec, rows, header_index + 1))
    return parsed


def parse_current_sheet(spec: SheetSpec, rows: Sequence[Sequence[str]]) -> ParsedSheet:
    report_date = extract_report_date(rows)
    parsed = _parse_tabular(
        spec,
        rows,
        asset_type=spec.asset_type or "reservoir",
        section="current_observations",
        report_date=report_date,
        required=("reservoir", "date"),
    )
    return parsed


def _mixed_header_kind(row: Sequence[str]) -> Optional[str]:
    values = {canonical_header(cell) for cell in row}
    joined = " ".join(values)
    if "anicut" in values:
        return "anicut"
    if values.intersection({"mediaum_tank", "medium_tank"}):
        return "small_tank"
    if "reservoir" in values and "fsd" not in joined and "gross_capacity" not in joined:
        if "water_level" in joined:
            return "other_tank"
    if "reservoir" in values and ("fsd" in joined or "gross_capacity" in joined):
        return "medium_reservoir"
    return None


def parse_mixed_sheet(spec: SheetSpec, rows: Sequence[Sequence[str]]) -> ParsedSheet:
    report_date = extract_report_date(rows)
    parsed = ParsedSheet(spec=spec, row_count=len(rows), report_date=report_date)
    headers_at: List[Tuple[int, str]] = []
    for index, row in enumerate(rows):
        kind = _mixed_header_kind(row)
        if kind:
            headers_at.append((index, kind))

    for position, (header_index, kind) in enumerate(headers_at):
        end = headers_at[position + 1][0] if position + 1 < len(headers_at) else len(rows)
        headers = unique_headers(rows[header_index])
        section = f"{kind}_{position + 1}"
        for index in range(header_index + 1, end):
            row = rows[index]
            if _is_blank(row):
                continue
            joined = " ".join(canonical_header(cell) for cell in row)
            if any(token in joined for token in ("notation", "prepared", "checked", "signed", "total")):
                continue
            record, issues = _record_from_row(
                spec,
                section=section,
                source_row=index + 1,
                headers=headers,
                row=row,
                asset_type=kind,
                report_date=report_date,
                season=None,
            )
            if record is not None:
                parsed.records.append(record)
                parsed.issues.extend(issues)
    return parsed


def parse_seasonal_sheet(spec: SheetSpec, rows: Sequence[Sequence[str]]) -> ParsedSheet:
    parsed = ParsedSheet(spec=spec, row_count=len(rows), report_date=None)
    header_index = _header_index(rows, ("reservoir", "date"))
    if header_index is None:
        parsed.issues.append(
            ParseIssue(
                sheet_name=spec.name,
                source_gid=spec.gid,
                source_row=None,
                section="seasonal_history",
                field=None,
                raw_value=None,
                code="header_not_found",
                message="Could not find the seasonal reservoir header",
                severity="error",
            )
        )
        return parsed

    headers = unique_headers(rows[header_index])
    for index in range(header_index + 1, len(rows)):
        row = rows[index]
        if _is_blank(row):
            continue
        record, issues = _record_from_row(
            spec,
            section="seasonal_history",
            source_row=index + 1,
            headers=headers,
            row=row,
            asset_type=spec.asset_type or "reservoir",
            report_date=None,
            season=spec.season,
            slash_order="mdy",
        )
        if record is not None and record.observed_date is not None:
            parsed.records.append(record)
            parsed.issues.extend(issues)
        elif record is not None:
            parsed.issues.append(
                ParseIssue(
                    sheet_name=spec.name,
                    source_gid=spec.gid,
                    source_row=index + 1,
                    section="seasonal_history",
                    field="updated_date",
                    raw_value=_field(record.raw_fields, "updated_date")
                    or _field(record.raw_fields, "update_date"),
                    code="date_not_parsed",
                    message="Seasonal row was skipped because its update date was not parsed",
                )
            )
    return parsed


def parse_idat_sheet(spec: SheetSpec, rows: Sequence[Sequence[str]]) -> ParsedSheet:
    parsed = ParsedSheet(spec=spec, row_count=len(rows), report_date=None)
    header_index = _header_index(rows, ("date", "reservoir_name"))
    if header_index is None:
        parsed.issues.append(
            ParseIssue(
                sheet_name=spec.name,
                source_gid=spec.gid,
                source_row=None,
                section="idat_snapshot",
                field=None,
                raw_value=None,
                code="header_not_found",
                message="Could not find the IDAT header",
                severity="error",
            )
        )
        return parsed
    headers = unique_headers(rows[header_index])
    for index in range(header_index + 1, len(rows)):
        if _is_blank(rows[index]):
            continue
        record, issues = _record_from_row(
            spec,
            section="idat_snapshot",
            source_row=index + 1,
            headers=headers,
            row=rows[index],
            asset_type=spec.asset_type or "major_reservoir",
            report_date=None,
        )
        if record is not None:
            parsed.records.append(record)
            parsed.issues.extend(issues)
            if parsed.report_date is None:
                parsed.report_date = record.observed_date
    return parsed


def parse_csv_text(spec: SheetSpec, text: str) -> ParsedSheet:
    rows = list(csv.reader(io.StringIO(text)))
    if spec.parser == "current":
        return parse_current_sheet(spec, rows)
    if spec.parser == "mixed":
        return parse_mixed_sheet(spec, rows)
    if spec.parser == "seasonal":
        return parse_seasonal_sheet(spec, rows)
    if spec.parser == "idat":
        return parse_idat_sheet(spec, rows)
    if spec.parser == "additional":
        return _parse_tabular(
            spec,
            rows,
            asset_type=spec.asset_type or "additional_reservoir",
            section="additional_observations",
            report_date=extract_report_date(rows),
            required=("reservoir", "date"),
        )
    raise ValueError(f"Unknown parser type: {spec.parser}")
