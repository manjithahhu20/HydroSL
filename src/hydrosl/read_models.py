from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .api import Warehouse, _overview


def asset_file_key(asset_id: str) -> str:
    """Return a stable, filesystem-safe key for an asset ID."""
    return asset_id.replace(":", "__")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _group_by(values: Iterable[Dict[str, Any]], key: str) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for value in values:
        group_key = value.get(key)
        if group_key is None:
            continue
        grouped.setdefault(str(group_key), []).append(value)
    return grouped


def export_read_models(warehouse: Path | str, output: Path | str) -> Dict[str, int]:
    """Export compact JSON files for a static dashboard deployment.

    The full warehouse remains available for local/API use. These read models
    are deliberately shaped around dashboard access patterns so the browser
    does not download the complete observation archive for every page load.
    """
    store = Warehouse(Path(warehouse))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    assets = store.assets()
    observations = store.observations()
    seasonal_references = store.seasonal_references()
    issues = store.issues()
    observation_groups = _group_by(observations, "asset_id")
    seasonal_groups = _group_by(seasonal_references, "asset_id")

    asset_views: List[Dict[str, Any]] = []
    for asset in assets:
        asset_view = dict(asset)
        key = asset_file_key(str(asset["asset_id"]))
        asset_view["data_path"] = f"assets/{key}.json"
        asset_views.append(asset_view)
        _write_json(
            output / "assets" / f"{key}.json",
            {
                "asset": asset_view,
                "observations": observation_groups.get(str(asset["asset_id"]), []),
                "seasonal_references": seasonal_groups.get(str(asset["asset_id"]), []),
            },
        )

    overview = _overview(store)
    _write_json(output / "overview.json", overview)
    _write_json(output / "assets.json", asset_views)
    _write_json(
        output / "quality.json",
        {
            "issue_count": len(issues),
            "issues": issues,
        },
    )
    source_manifest = store.manifest()
    _write_json(
        output / "manifest.json",
        {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_run_id": source_manifest.get("run_id"),
            "source_fetched_at": source_manifest.get("fetched_at"),
            "counts": {
                "assets": len(assets),
                "observations": len(observations),
                "seasonal_references": len(seasonal_references),
                "issues": len(issues),
            },
            "files": {
                "overview": "overview.json",
                "assets": "assets.json",
                "quality": "quality.json",
            },
        },
    )
    return {
        "assets": len(assets),
        "observations": len(observations),
        "seasonal_references": len(seasonal_references),
        "issues": len(issues),
    }
