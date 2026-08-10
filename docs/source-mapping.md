# Google Sheets Source Mapping

The initial workbook is configured in `src/hydrosl/sheets.py`.

| Sheet | GID | Parser | Domain sections |
|---|---:|---|---|
| Major | 1212294664 | current | major reservoirs and regional summaries |
| Medium | 562386515 | current | medium reservoirs and regional summaries |
| Sheet3 | 1461987010 | mixed | medium reservoirs, anicuts, other tanks, small tanks |
| Sheet4 | 1883578062 | additional | additional medium/small reservoirs |
| Major_Yala | 1244158041 | seasonal | Yala major history and reference columns |
| Medium_Yala | 1831537855 | seasonal | Yala medium history and reference columns |
| IDAT | 217395621 | idat | major-reservoir operational snapshot |
| Major_Maha | 673998835 | seasonal | Maha major history and reference columns |
| Medium_Maha | 155979206 | seasonal | Maha medium history and reference columns |

The source has known irregularities: names vary between sheets, `NO` resets by
date, some rows are stale, some cells contain spill text instead of numeric
water depth, and formula errors such as `#REF!` and `#DIV/0!` occur. The raw
archive retains these values and the parser emits quality issues.

The source is a published workbook used with permission. The code license does
not replace the source owner's data terms.

Dashboard read models expose structured current values, daily seasonal history,
regional summaries, operational records, source provenance, and data-quality
issues. Rows dated after the ingestion fetch date are retained but hidden from
default current and history views.
