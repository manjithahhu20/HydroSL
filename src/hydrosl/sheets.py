from __future__ import annotations

from .models import SheetSpec


PUBLISHED_WORKBOOK_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vTcSGhi9RESl7CMCl1TQnrKe07Gx5Q696YiSB9jneIHqIP9lifpqSErgI3D5k9KtQXSdW5JpycIIr5e/pub"
)


SHEET_SPECS = (
    SheetSpec("Major", "1212294664", "current", "major_reservoir"),
    SheetSpec("Medium", "562386515", "current", "medium_reservoir"),
    SheetSpec("Sheet3", "1461987010", "mixed"),
    SheetSpec("Sheet4", "1883578062", "additional", "additional_reservoir"),
    SheetSpec("Major_Yala", "1244158041", "seasonal", "major_reservoir", "Yala"),
    SheetSpec("Medium_Yala", "1831537855", "seasonal", "medium_reservoir", "Yala"),
    SheetSpec("IDAT", "217395621", "idat", "major_reservoir"),
    SheetSpec("Major_Maha", "673998835", "seasonal", "major_reservoir", "Maha"),
    SheetSpec("Medium_Maha", "155979206", "seasonal", "medium_reservoir", "Maha"),
)


SHEET_BY_NAME = {spec.name: spec for spec in SHEET_SPECS}
