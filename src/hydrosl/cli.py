from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Sequence

from .archive import archive_snapshot, utc_now, write_json, write_warehouse
from .models import ParseIssue, ParsedSheet, SheetSpec, SnapshotInfo
from .normalization import normalize
from .parsing import parse_csv_text
from .sheets import PUBLISHED_WORKBOOK_URL, SHEET_BY_NAME, SHEET_SPECS
from .source import GoogleSheetsSource, SourceFetchError


def _run_id(now: datetime | None = None) -> str:
    now = now or utc_now()
    return now.strftime("%Y%m%dT%H%M%SZ")


def _selected_specs(names: Sequence[str] | None) -> List[SheetSpec]:
    if not names:
        return list(SHEET_SPECS)
    unknown = [name for name in names if name not in SHEET_BY_NAME]
    if unknown:
        raise ValueError(f"unknown sheet(s): {', '.join(unknown)}")
    return [SHEET_BY_NAME[name] for name in names]


def _error_snapshot(spec: SheetSpec, source: GoogleSheetsSource, error: Exception) -> SnapshotInfo:
    return SnapshotInfo(
        sheet_name=spec.name,
        gid=spec.gid,
        url=source.url_for(spec),
        path="",
        sha256="",
        bytes=0,
        fetched_at=utc_now(),
        status="error",
        error=str(error),
    )


def _manifest(
    *,
    run_id: str,
    source: GoogleSheetsSource,
    snapshots: Iterable[SnapshotInfo],
    parsed: Iterable[ParsedSheet],
    output: Path,
) -> dict:
    parsed = list(parsed)
    snapshot_values = list(snapshots)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "fetched_at": datetime.now(timezone.utc),
        "workbook_url": source.workbook_url,
        "output_dir": str(output),
        "sheets": snapshot_values,
        "parsed": [
            {
                "sheet_name": item.spec.name,
                "gid": item.spec.gid,
                "row_count": item.row_count,
                "record_count": len(item.records),
                "summary_count": len(item.summaries),
                "issue_count": len(item.issues),
                "report_date": item.report_date,
            }
            for item in parsed
        ],
    }


def ingest(
    *,
    output: Path,
    specs: Sequence[SheetSpec],
    workbook_url: str = PUBLISHED_WORKBOOK_URL,
    continue_on_error: bool = True,
) -> int:
    run_id = _run_id()
    source = GoogleSheetsSource(workbook_url)
    snapshots: List[SnapshotInfo] = []
    parsed_sheets: List[ParsedSheet] = []
    failures: List[str] = []

    for spec in specs:
        print(f"Fetching {spec.name} ({spec.gid}) ...")
        try:
            text = source.fetch(spec)
            snapshot = archive_snapshot(
                output,
                run_id=run_id,
                sheet_name=spec.name,
                gid=spec.gid,
                url=source.url_for(spec),
                text=text,
            )
            parsed = parse_csv_text(spec, text)
            snapshots.append(snapshot)
            parsed_sheets.append(parsed)
            print(
                f"  rows={parsed.row_count} records={len(parsed.records)} "
                f"summaries={len(parsed.summaries)} issues={len(parsed.issues)}"
            )
        except (SourceFetchError, OSError, ValueError) as exc:
            failures.append(f"{spec.name}: {exc}")
            snapshots.append(_error_snapshot(spec, source, exc))
            print(f"  ERROR: {exc}", file=sys.stderr)
            if not continue_on_error:
                break

    dataset = normalize(parsed_sheets)
    manifest = _manifest(
        run_id=run_id,
        source=source,
        snapshots=snapshots,
        parsed=parsed_sheets,
        output=output,
    )
    manifest["counts"] = {
        "assets": len(dataset.assets),
        "records": len(dataset.records),
        "observations": len(dataset.observations),
        "seasonal_references": len(dataset.seasonal_references),
        "summaries": len(dataset.summaries),
        "issues": len(dataset.issues),
    }
    write_warehouse(output, dataset, manifest)
    write_json(output / "runs" / f"{run_id}.json", manifest)

    print(json.dumps(manifest["counts"], indent=2))
    if failures:
        print("Ingestion failures:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


def parse_archived(
    *, output: Path, run_id: str, specs: Sequence[SheetSpec]
) -> int:
    raw_dir = output / "raw" / run_id
    if not raw_dir.exists():
        print(f"raw run does not exist: {raw_dir}", file=sys.stderr)
        return 1
    parsed_sheets: List[ParsedSheet] = []
    snapshots: List[SnapshotInfo] = []
    source = GoogleSheetsSource()
    for spec in specs:
        path = raw_dir / f"{spec.name}.csv"
        if not path.exists():
            print(f"missing raw sheet: {path}", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8-sig")
        parsed_sheets.append(parse_csv_text(spec, text))
        snapshots.append(
            SnapshotInfo(
                sheet_name=spec.name,
                gid=spec.gid,
                url=source.url_for(spec),
                path=str(path),
                sha256="",
                bytes=path.stat().st_size,
                fetched_at=utc_now(),
            )
        )
    dataset = normalize(parsed_sheets)
    manifest = _manifest(
        run_id=run_id,
        source=source,
        snapshots=snapshots,
        parsed=parsed_sheets,
        output=output,
    )
    manifest["counts"] = {
        "assets": len(dataset.assets),
        "records": len(dataset.records),
        "observations": len(dataset.observations),
        "seasonal_references": len(dataset.seasonal_references),
        "summaries": len(dataset.summaries),
        "issues": len(dataset.issues),
    }
    write_warehouse(output, dataset, manifest)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hydrosl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="fetch and normalize all configured sheets")
    ingest_parser.add_argument("--output", type=Path, default=Path("data/warehouse"))
    ingest_parser.add_argument("--sheet", action="append", dest="sheets")
    ingest_parser.add_argument("--workbook-url", default=PUBLISHED_WORKBOOK_URL)
    ingest_parser.add_argument(
        "--fail-fast", action="store_true", help="stop after the first source failure"
    )

    parse_parser = subparsers.add_parser("parse", help="reprocess an archived raw run")
    parse_parser.add_argument("run_id")
    parse_parser.add_argument("--output", type=Path, default=Path("data/warehouse"))
    parse_parser.add_argument("--sheet", action="append", dest="sheets")

    serve_parser = subparsers.add_parser("serve", help="start the optional FastAPI service")
    serve_parser.add_argument("--warehouse", type=Path, default=Path("data/warehouse"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    list_parser = subparsers.add_parser("list-sheets", help="list configured workbook sheets")
    list_parser.add_argument("--workbook-url", default=PUBLISHED_WORKBOOK_URL)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest":
        code = ingest(
            output=args.output,
            specs=_selected_specs(args.sheets),
            workbook_url=args.workbook_url,
            continue_on_error=not args.fail_fast,
        )
        raise SystemExit(code)
    if args.command == "parse":
        raise SystemExit(
            parse_archived(output=args.output, run_id=args.run_id, specs=_selected_specs(args.sheets))
        )
    if args.command == "list-sheets":
        for spec in SHEET_SPECS:
            print(f"{spec.name}\t{spec.gid}\t{spec.parser}\t{spec.season or ''}")
        return
    if args.command == "serve":
        try:
            import uvicorn
        except ImportError as exc:
            raise SystemExit("Install the API extras first: python -m pip install -e '.[api]'") from exc
        from .api import create_app

        uvicorn.run(create_app(args.warehouse), host=args.host, port=args.port)
