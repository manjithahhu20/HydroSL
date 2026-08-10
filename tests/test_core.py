from __future__ import annotations

import tempfile
import unittest
from datetime import date
import json
from pathlib import Path

from hydrosl.archive import archive_snapshot
from hydrosl.models import MetricValue, SheetSpec, SourceRecord
from hydrosl.normalization import normalize
from hydrosl.parsing import parse_csv_text, parse_number
from hydrosl.read_models import export_read_models
from hydrosl.sheets import SHEET_SPECS


class ParsingTests(unittest.TestCase):
    def test_number_parser_preserves_missing_and_source_errors(self) -> None:
        self.assertEqual(parse_number("1,234.50"), (1234.5, "observed"))
        self.assertEqual(parse_number("-"), (None, "missing"))
        self.assertEqual(parse_number("#REF!"), (None, "source_error"))
        self.assertEqual(parse_number('12" Spill'), (None, "textual_value"))

    def test_current_sheet_extracts_report_and_metrics(self) -> None:
        text = """IRRIGATION DEPARTMENT,,,,
DAILY WATER LEVEL & STORAGE OF MAJOR RESERVOIRS,,,,
10th of August 2026 to 16th of August 2026,,,,
NO,RESERVOIR,RANGE,DATE,WATER DEPTH (ft),GROSS STORAGE (Acft),EFFECTIVE STORAGE %,spilling,REMARKS
1,Yan Oya,ANURADAPURA,10-Aug,15.06,"71,956",42.7%,No,LB=0
2,Ambewela,BADULLA,9-Aug,18.17,"2,050",100.0%,Yes,Spill

SUMMARY OF DAILY WATER LEVEL & STORAGE,,,,
NO,RANGE,STORAGE (Acft),,,,,
1,ANURADAPURA,291526,,,,,
"""
        spec = SheetSpec("Major", "1", "current", "major_reservoir")
        parsed = parse_csv_text(spec, text)
        self.assertEqual(parsed.report_date, date(2026, 8, 10))
        self.assertEqual(len(parsed.records), 2)
        self.assertEqual(parsed.records[0].observed_date, date(2026, 8, 10))
        self.assertEqual(parsed.records[0].metrics["gross_storage_acft"].value, 71956.0)
        self.assertEqual(parsed.records[1].metrics["spilling"].text_value, "Yes")
        self.assertEqual(len(parsed.summaries), 1)
        self.assertEqual(parsed.summaries[0].values["scope"], "ANURADAPURA")

    def test_mixed_sheet_keeps_asset_sections(self) -> None:
        text = """IRRIGATION DEPARTMENT,
10th of August 2026 to 16th of August 2026,
NO,RESERVOIR,RANGE,FSD (ft),GROSS CAPACITY (Acft),DATE,WATER DEPTH (ft)
1,Tank A,A,10,100,10-Aug,4

No,Anicut,RANGE,DATE,Water level,Spilling,Sluice,Rainfall(mm),Remarks
1,Anicut A,A,10-Aug,5.2,No,0,2.0,

No,RESERVOIR,RANGE,DATE,Water level,GROSS STORAGE (Acft),Spilling
1,Tank B,B,10-Aug,3.0,42,No

No.,Mediaum Tank,Division,Gross Capacity (Acft),Dead Storage (Acft),FSL (mMSL),Gross Extent (ac),Present storage
1,Tank C,Colombo,50,5,12.4,100,20
"""
        spec = SheetSpec("Sheet3", "2", "mixed")
        parsed = parse_csv_text(spec, text)
        self.assertEqual(len(parsed.records), 4)
        self.assertEqual(
            {record.asset_type for record in parsed.records},
            {"medium_reservoir", "anicut", "other_tank", "small_tank"},
        )
        small = next(record for record in parsed.records if record.asset_type == "small_tank")
        self.assertEqual(small.metrics["present_storage_acft"].value, 20.0)

    def test_seasonal_columns_are_separate_references(self) -> None:
        text = """NO,UPDATED DATE,RESERVOIR,LATITUDE,LONGITUDE,RANGE,Active Storage (Acft),Long Term Avarage,EFFECTIVE STORAGE (Acft) 2022,EFFECTIVE STORAGE (Acft) 2026
1,4/1/2026,Yan Oya,8.72,80.88,A,104176,110572,129376,104176
"""
        spec = SheetSpec("Major_Yala", "3", "seasonal", "major_reservoir", "Yala")
        parsed = parse_csv_text(spec, text)
        self.assertEqual(len(parsed.records), 1)
        record = parsed.records[0]
        self.assertEqual(record.observed_date, date(2026, 4, 1))
        self.assertEqual(set(record.seasonal_references), {"2022", "2026"})
        self.assertEqual(record.metrics["active_storage_acft"].value, 104176.0)

    def test_small_tank_two_row_header_and_idat_units(self) -> None:
        mixed = """IRRIGATION DEPARTMENT,
No.,Mediaum Tank,Division,,,,,
,,,,Details of the tank,,,,Present storage,
1,Tank C,Colombo,,50,5,12.4,100,20
"""
        mixed_spec = SheetSpec("Sheet3", "4", "mixed")
        mixed_parsed = parse_csv_text(mixed_spec, mixed)
        small = mixed_parsed.records[0]
        self.assertEqual(small.metrics["gross_capacity_acft"].value, 50.0)
        self.assertEqual(small.metrics["present_storage_acft"].value, 20.0)

        idat = """Date,Reservoir Name,Water Depth(m),Gross Storage(Acft),Spilling (Y/N)
10-Aug-26,Tank C,13.60,100,No
"""
        idat_spec = SheetSpec("IDAT", "5", "idat", "major_reservoir")
        idat_parsed = parse_csv_text(idat_spec, idat)
        self.assertEqual(idat_parsed.report_date, date(2026, 8, 10))
        self.assertEqual(idat_parsed.records[0].report_date, date(2026, 8, 10))
        self.assertEqual(idat_parsed.records[0].metrics["water_depth_m"].unit, "m")


class NormalizationTests(unittest.TestCase):
    def test_aliases_match_across_source_names(self) -> None:
        records = [
            SourceRecord(
                sheet_name="Major",
                gid="1",
                section="current",
                source_row=1,
                asset_type="major_reservoir",
                asset_name="Yan Oya",
                observed_date=date(2026, 8, 10),
                report_date=date(2026, 8, 10),
                season=None,
                raw_fields={"RESERVOIR": "Yan Oya", "LATITUDE": "8.72", "LONGITUDE": "80.88"},
                metrics={
                    "effective_storage_pct": MetricValue(
                        "effective_storage_pct", "42.7%", 42.7, "%"
                    )
                },
            ),
            SourceRecord(
                sheet_name="IDAT",
                gid="2",
                section="snapshot",
                source_row=1,
                asset_type="major_reservoir",
                asset_name="Yanoya",
                observed_date=date(2026, 8, 10),
                report_date=date(2026, 8, 10),
                season=None,
                raw_fields={"Reservoir Name": "Yanoya"},
                metrics={},
            ),
        ]
        dataset = normalize([
            type("Parsed", (), {"records": records, "summaries": [], "issues": []})()
        ])
        self.assertEqual(len(dataset.assets), 1)
        self.assertEqual(dataset.assets[0].asset_id, "major_reservoir:yanoya")
        self.assertEqual(set(dataset.assets[0].aliases), {"Yan Oya", "Yanoya"})


class ArchiveTests(unittest.TestCase):
    def test_snapshot_archive_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            info = archive_snapshot(
                Path(directory),
                run_id="run",
                sheet_name="Major",
                gid="1",
                url="https://example.test",
                text="a,b\n1,2\n",
            )
            self.assertTrue(Path(info.path).exists())
            self.assertEqual(info.bytes, len("a,b\n1,2\n".encode()))
            self.assertEqual(len(info.sha256), 64)

    def test_read_models_export_dashboard_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            warehouse = Path(directory) / "warehouse"
            output = Path(directory) / "dashboard-data"
            warehouse.mkdir()
            (warehouse / "manifest.json").write_text(
                json.dumps({"run_id": "run", "fetched_at": "2026-08-10T00:00:00+00:00"}),
                encoding="utf-8",
            )
            (warehouse / "assets.jsonl").write_text(
                json.dumps({"asset_id": "major_reservoir:test", "canonical_name": "Test"}) + "\n",
                encoding="utf-8",
            )
            (warehouse / "observations.jsonl").write_text(
                json.dumps({
                    "asset_id": "major_reservoir:test",
                    "metric_code": "effective_storage_pct",
                    "observed_date": "2026-08-10",
                    "value": 42.0,
                }) + "\n",
                encoding="utf-8",
            )
            (warehouse / "seasonal_references.jsonl").write_text("", encoding="utf-8")
            (warehouse / "issues.jsonl").write_text("", encoding="utf-8")
            counts = export_read_models(warehouse, output)
            self.assertEqual(counts["assets"], 1)
            self.assertTrue((output / "overview.json").exists())
            self.assertTrue((output / "assets" / "major_reservoir__test.json").exists())


class RegistryTests(unittest.TestCase):
    def test_all_nine_source_sheets_are_registered(self) -> None:
        self.assertEqual(len(SHEET_SPECS), 9)
        self.assertEqual({spec.name for spec in SHEET_SPECS}, {
            "Major", "Medium", "Sheet3", "Sheet4", "Major_Yala",
            "Medium_Yala", "IDAT", "Major_Maha", "Medium_Maha",
        })


if __name__ == "__main__":
    unittest.main()
