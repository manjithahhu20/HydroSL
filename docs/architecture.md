# Architecture

HydroSL is organized around a stable domain model rather than around one
source workbook.

```text
Source adapter
  -> raw snapshot archive
  -> source-specific parser
  -> SourceRecord
  -> entity resolver
  -> Asset / Observation / SeasonalReference
  -> API
  -> dashboard feature
```

## Source adapters

Each adapter is responsible for fetching and identifying a source. It must
return raw text and source metadata. A parser converts that text into
`SourceRecord` values. A source-specific parser may understand irregular
headers and sections, but it must not contain dashboard logic.

## Domain layer

The domain layer uses generic assets and metric values. A new source can map to
existing metric codes, while a future feature can introduce new metric codes
through a registry without changing the source adapter.

Derived indicators should be separate from raw observations. Each derived
result should record its input period, method, assumptions, and calculation
version.

## Storage

The initial warehouse is JSON Lines so it is inspectable with standard tools and
requires no database server. DuckDB/Parquet or PostgreSQL/PostGIS can be added
behind the same API when query volume, geospatial operations, or concurrent
writes justify it.

Raw snapshots and normalized files are runtime artifacts and are ignored by
Git by default. Small, representative fixtures belong in `data/samples/` and
are used by tests.

## Adding a future feature

1. Define the asset, metric, or derived-indicator contract.
2. Add source mappings or a calculation module.
3. Add quality rules and fixtures.
4. Add versioned API output.
5. Add a dashboard view that consumes the API.

The first feature is reservoir and water-resource monitoring. Drought indices,
crop demand, river gauges, groundwater, forecasting, and alerts can follow the
same path.
