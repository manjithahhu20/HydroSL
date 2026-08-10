# HydroSL

HydroSL is an open-source hydrology data platform for Sri Lanka. The first
vertical slice ingests the Irrigation Department's published reservoir
workbook, preserves the source sheets, normalizes reservoir and water-resource
observations, and exposes them to a dashboard API.

The project is intentionally split into source adapters, a reusable domain
model, quality checks, an API, and dashboard features. Future sources and
features such as drought indices, crop water demand, river gauges, and
forecasting can be added without coupling them to the Google Sheets parser.

## Current source

The initial source is the permissioned published workbook:

<https://docs.google.com/spreadsheets/d/e/2PACX-1vTcSGhi9RESl7CMCl1TQnrKe07Gx5Q696YiSB9jneIHqIP9lifpqSErgI3D5k9KtQXSdW5JpycIIr5e/pub>

HydroSL fetches each sheet through its published CSV export. Raw snapshots are
kept separately from normalized data, and source-specific parsing warnings are
never silently discarded.

## Quick start

Create an environment and install the package:

```text
python -m venv .venv
python -m pip install -e ".[api,dev]"
```

Run an ingestion job:

```text
hydrosl ingest --output data/warehouse
```

The command archives raw sheet snapshots below `data/warehouse/raw/` and
writes normalized JSON Lines files below `data/warehouse/`.

Start the API:

```text
hydrosl serve --warehouse data/warehouse
```

The API is available at `http://localhost:8000`. From the repository root,
serve the dashboard and documentation with:

```text
python -m http.server 5173
```

Open `http://localhost:5173/apps/dashboard/`.

## Architecture

```text
Source adapter -> raw snapshots -> sheet parsers -> normalized records
                                      -> quality issues
                                      -> API -> dashboard features
```

The normalized model uses generic assets, observations, metrics, seasonal
references, summaries, and provenance. New metrics do not require a new
spreadsheet-specific table.

## Data policy

Raw source values are retained alongside parsed values. Blank cells, `-`, zero,
textual measurements, and source errors such as `#REF!` are different states.
The dashboard must show freshness and quality status, and should not be used as
an official emergency warning service without appropriate agency validation.

The code is MIT licensed. Source data remains subject to the source owner's
permission and any applicable data terms.
