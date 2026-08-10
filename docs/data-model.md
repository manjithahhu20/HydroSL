# Data Model

## Asset

An `Asset` is a water-resource entity such as a major reservoir, medium
reservoir, anicut, or tank. It has a stable HydroSL ID, a canonical name, a
list of source aliases, optional coordinates, administrative fields, and
source keys.

## Observation

An `Observation` is a value for one asset and one metric at one source date.
It contains:

- `asset_id`
- `metric_code`
- `observed_date`
- `report_date`
- `value`
- `unit`
- `raw_value`
- `quality_flag`
- source sheet, `gid`, section, and row
- optional text value and source attributes

The report date and the measurement date are separate because the workbook
often contains stale readings inside a current report.

## Metric codes

The first release includes codes for storage, water depth, FSD, gross extent,
rainfall, spilling, sluice discharge, diversion, outflow, and seasonal
references. Codes are strings rather than a closed database enum so future
variables such as discharge, evapotranspiration, groundwater level, SPI, and
crop demand can be added without a schema rewrite.

## Quality flags

`observed`, `observed_text`, `missing`, `textual_value`, and `source_error` are
kept distinct. A raw source value is never replaced by a guessed numeric value.

## Seasonal references

Yala and Maha comparison columns are stored as long-form seasonal references.
The source column label remains available as `reference_period`; HydroSL does
not invent dates that the source does not provide.
