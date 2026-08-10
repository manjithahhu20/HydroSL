from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    values: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                values.append(json.loads(line))
    return values


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class Warehouse:
    def __init__(self, root: Path) -> None:
        self.root = root

    def manifest(self) -> Dict[str, Any]:
        return _read_json(self.root / "manifest.json")

    def assets(self) -> List[Dict[str, Any]]:
        return _read_jsonl(self.root / "assets.jsonl")

    def observations(self) -> List[Dict[str, Any]]:
        return _read_jsonl(self.root / "observations.jsonl")

    def seasonal_references(self) -> List[Dict[str, Any]]:
        return _read_jsonl(self.root / "seasonal_references.jsonl")

    def summaries(self) -> List[Dict[str, Any]]:
        return _read_jsonl(self.root / "summaries.jsonl")

    def issues(self) -> List[Dict[str, Any]]:
        return _read_jsonl(self.root / "issues.jsonl")

    def cutoff_date(self) -> Optional[date]:
        fetched_at = self.manifest().get("fetched_at")
        if not fetched_at:
            return None
        try:
            return date.fromisoformat(str(fetched_at)[:10])
        except ValueError:
            return None

    def observations_at_fetch_time(self) -> List[Dict[str, Any]]:
        cutoff = self.cutoff_date()
        if cutoff is None:
            return self.observations()
        result: List[Dict[str, Any]] = []
        for observation in self.observations():
            observed_date = observation.get("observed_date")
            if not observed_date:
                result.append(observation)
                continue
            try:
                if date.fromisoformat(str(observed_date)) <= cutoff:
                    result.append(observation)
            except ValueError:
                result.append(observation)
        return result


def _date_key(value: Optional[str]) -> str:
    return value or ""


def _latest_by_asset_metric(observations: Iterable[Dict[str, Any]]) -> Dict[tuple, Dict[str, Any]]:
    latest: Dict[tuple, Dict[str, Any]] = {}
    for observation in observations:
        key = (observation.get("asset_id"), observation.get("metric_code"))
        current = latest.get(key)
        if current is None or _date_key(observation.get("observed_date")) > _date_key(
            current.get("observed_date")
        ):
            latest[key] = observation
    return latest


def _overview(warehouse: Warehouse) -> Dict[str, Any]:
    assets = warehouse.assets()
    observations = warehouse.observations_at_fetch_time()
    latest = _latest_by_asset_metric(observations)
    asset_types: Dict[str, int] = {}
    for asset in assets:
        asset_type = asset.get("asset_type", "unknown")
        asset_types[asset_type] = asset_types.get(asset_type, 0) + 1

    storage_total = 0.0
    effective_total = 0.0
    percent_values: List[float] = []
    spilling = 0
    for key, observation in latest.items():
        metric = key[1]
        value = observation.get("value")
        if metric in {"gross_storage_acft", "active_storage_acft", "effective_storage_acft"} and isinstance(value, (int, float)):
            if metric == "effective_storage_acft":
                effective_total += float(value)
            elif metric == "gross_storage_acft":
                storage_total += float(value)
        if metric == "effective_storage_pct" and isinstance(value, (int, float)):
            percent_values.append(float(value))
        if metric == "spilling" and (observation.get("text_value") or "").lower() == "yes":
            spilling += 1

    report_dates = [item.get("report_date") for item in observations if item.get("report_date")]
    observed_dates = [item.get("observed_date") for item in observations if item.get("observed_date")]
    return {
        "asset_count": len(assets),
        "asset_types": asset_types,
        "latest_report_date": max(report_dates) if report_dates else None,
        "latest_observed_date": max(observed_dates) if observed_dates else None,
        "gross_storage_acft_total": storage_total,
        "effective_storage_acft_total": effective_total,
        "average_effective_storage_pct": (
            sum(percent_values) / len(percent_values) if percent_values else None
        ),
        "reservoirs_spilling": spilling,
        "quality_issue_count": len(warehouse.issues()),
    }


def create_app(warehouse: Path | str = Path("data/warehouse")):
    """Create the API application.

    FastAPI is optional so ingestion and parsing remain usable in lightweight
    environments. Importing this function does not require the API extras.
    """
    try:
        from fastapi import FastAPI, Query
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:
        raise RuntimeError("Install the API extras with: pip install -e '.[api]'") from exc

    root = Path(warehouse)
    store = Warehouse(root)
    app = FastAPI(title="HydroSL API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    def health() -> Dict[str, Any]:
        manifest = store.manifest()
        return {
            "status": "ok" if manifest else "empty",
            "warehouse": str(root),
            "run_id": manifest.get("run_id"),
            "counts": manifest.get("counts", {}),
        }

    @app.get("/api/v1/overview")
    def overview() -> Dict[str, Any]:
        return _overview(store)

    @app.get("/api/v1/assets")
    def assets(
        asset_type: Optional[str] = None,
        district: Optional[str] = None,
        range_name: Optional[str] = Query(default=None, alias="range"),
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        result = store.assets()
        if asset_type:
            result = [item for item in result if item.get("asset_type") == asset_type]
        if district:
            result = [item for item in result if item.get("district") == district]
        if range_name:
            result = [item for item in result if item.get("range_name") == range_name]
        if search:
            needle = search.casefold()
            result = [
                item
                for item in result
                if needle in str(item.get("canonical_name", "")).casefold()
                or any(needle in alias.casefold() for alias in item.get("aliases", []))
            ]
        return result

    @app.get("/api/v1/assets/{asset_id:path}")
    def asset(asset_id: str) -> Dict[str, Any]:
        for item in store.assets():
            if item.get("asset_id") == asset_id:
                return item
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Asset not found")

    @app.get("/api/v1/observations")
    def observations(
        asset_id: Optional[str] = None,
        metric_code: Optional[str] = None,
        season: Optional[str] = None,
        from_date: Optional[str] = Query(default=None, alias="from"),
        to_date: Optional[str] = Query(default=None, alias="to"),
        include_future: bool = False,
        limit: int = Query(default=5000, ge=1, le=100000),
    ) -> List[Dict[str, Any]]:
        result = store.observations()
        if not include_future:
            result = [
                item
                for item in result
                if item.get("observed_date") is None
                or store.cutoff_date() is None
                or _date_key(item.get("observed_date")) <= store.cutoff_date().isoformat()
            ]
        if asset_id:
            result = [item for item in result if item.get("asset_id") == asset_id]
        if metric_code:
            result = [item for item in result if item.get("metric_code") == metric_code]
        if season:
            result = [item for item in result if item.get("season") == season]
        if from_date:
            result = [item for item in result if _date_key(item.get("observed_date")) >= from_date]
        if to_date:
            result = [item for item in result if _date_key(item.get("observed_date")) <= to_date]
        result.sort(key=lambda item: (_date_key(item.get("observed_date")), item.get("asset_id", "")))
        return result[:limit]

    @app.get("/api/v1/seasonal-references")
    def seasonal_references(
        asset_id: Optional[str] = None,
        season: Optional[str] = None,
        reference_period: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        result = store.seasonal_references()
        if asset_id:
            result = [item for item in result if item.get("asset_id") == asset_id]
        if season:
            result = [item for item in result if item.get("season") == season]
        if reference_period:
            result = [item for item in result if item.get("reference_period") == reference_period]
        return result

    @app.get("/api/v1/issues")
    def issues(limit: int = Query(default=500, ge=1, le=10000)) -> List[Dict[str, Any]]:
        return store.issues()[:limit]

    return app
