from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import SnapshotInfo
from .serialization import to_jsonable


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def archive_snapshot(
    output_dir: Path,
    *,
    run_id: str,
    sheet_name: str,
    gid: str,
    url: str,
    text: str,
    fetched_at: datetime | None = None,
) -> SnapshotInfo:
    fetched_at = fetched_at or utc_now()
    digest = sha256_text(text)
    path = output_dir / "raw" / run_id / f"{sheet_name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return SnapshotInfo(
        sheet_name=sheet_name,
        gid=gid,
        url=url,
        path=str(path),
        sha256=digest,
        bytes=len(text.encode("utf-8")),
        fetched_at=fetched_at,
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: Iterable[Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(json.dumps(to_jsonable(value), sort_keys=True) + "\n")
            count += 1
    return count


def write_warehouse(output_dir: Path, dataset: Any, manifest: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "manifest.json", manifest)
    write_jsonl(output_dir / "assets.jsonl", dataset.assets)
    write_jsonl(output_dir / "records.jsonl", dataset.records)
    write_jsonl(output_dir / "observations.jsonl", dataset.observations)
    write_jsonl(output_dir / "seasonal_references.jsonl", dataset.seasonal_references)
    write_jsonl(output_dir / "summaries.jsonl", dataset.summaries)
    write_jsonl(output_dir / "issues.jsonl", dataset.issues)
