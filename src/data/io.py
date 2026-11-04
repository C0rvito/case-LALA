from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from .config import FOLLOWUP_PATH, SHEETS, WORKBOOK_PATH


@dataclass
class SheetMeta:
    sheet: str
    state: str
    dimensions: str
    rows: int
    columns: int
    merged_ranges: int
    freeze_panes: str | None
    hidden_rows: int
    hidden_columns: int
    formula_cells: int


@dataclass
class DataBundle:
    responses: pd.DataFrame
    scoring: pd.DataFrame
    summary: pd.DataFrame
    sheet3: pd.DataFrame
    final: pd.DataFrame
    followup: pd.DataFrame
    formula_audit: pd.DataFrame
    sheet_meta: pd.DataFrame
    source_paths: dict[str, Path] = field(default_factory=dict)


class WorkbookAuditor:
    def __init__(self, path: Path = WORKBOOK_PATH):
        self.path = path

    def formula_audit(self) -> pd.DataFrame:
        formula_book = load_workbook(self.path, data_only=False)
        cached_book = load_workbook(self.path, data_only=True)
        rows: list[dict] = []
        for sheet in formula_book.sheetnames:
            ws_formula = formula_book[sheet]
            ws_cached = cached_book[sheet]
            for row in ws_formula.iter_rows():
                for cell in row:
                    value = cell.value
                    cached = ws_cached[cell.coordinate].value
                    if isinstance(value, str) and value.startswith("="):
                        if isinstance(cached, str) and cached.startswith("#"):
                            status = "error"
                        elif cached is None:
                            status = "no cached value"
                        else:
                            status = "ok"
                        rows.append(
                            {
                                "kind": "formula",
                                "sheet": sheet,
                                "cell": cell.coordinate,
                                "formula": value,
                                "cached_value": cached,
                                "status": status,
                            }
                        )
                    elif cell.data_type == "e" or (
                        isinstance(value, str) and value.startswith("#")
                    ):
                        rows.append(
                            {
                                "kind": "error",
                                "sheet": sheet,
                                "cell": cell.coordinate,
                                "formula": "",
                                "cached_value": value,
                                "status": "error",
                            }
                        )
        return pd.DataFrame(
            rows,
            columns=[
                "kind",
                "sheet",
                "cell",
                "formula",
                "cached_value",
                "status",
            ],
        )

    def sheet_meta(self) -> pd.DataFrame:
        book = load_workbook(self.path, data_only=False)
        rows: list[dict] = []
        for ws in book.worksheets:
            formula_cells = sum(
                1
                for row in ws.iter_rows()
                for cell in row
                if isinstance(cell.value, str) and cell.value.startswith("=")
            )
            rows.append(
                {
                    "sheet": ws.title,
                    "state": ws.sheet_state,
                    "dimensions": ws.dimensions,
                    "rows": ws.max_row,
                    "columns": ws.max_column,
                    "merged_ranges": len(ws.merged_cells.ranges),
                    "freeze_panes": str(ws.freeze_panes) if ws.freeze_panes else "",
                    "hidden_rows": sum(
                        1 for dim in ws.row_dimensions.values() if dim.hidden
                    ),
                    "hidden_columns": sum(
                        1 for dim in ws.column_dimensions.values() if dim.hidden
                    ),
                    "formula_cells": formula_cells,
                }
            )
        return pd.DataFrame(rows)


class ExcelLoader:
    def __init__(self, path: Path = WORKBOOK_PATH):
        self.path = path

    def load(self) -> dict[str, pd.DataFrame]:
        return {
            "responses": pd.read_excel(
                self.path, sheet_name=SHEETS["responses"], header=1, engine="openpyxl"
            ),
            "scoring": pd.read_excel(
                self.path, sheet_name=SHEETS["scoring"], header=0, engine="openpyxl"
            ),
            "summary": pd.read_excel(
                self.path, sheet_name=SHEETS["summary"], header=None, engine="openpyxl"
            ),
            "sheet3": pd.read_excel(
                self.path, sheet_name=SHEETS["sheet3"], header=None, engine="openpyxl"
            ),
            "final": pd.read_excel(
                self.path, sheet_name=SHEETS["final"], header=0, engine="openpyxl"
            ),
        }


class FollowupLoader:
    def __init__(self, path: Path = FOLLOWUP_PATH):
        self.path = path

    def load(self) -> pd.DataFrame:
        return pd.read_csv(self.path, dtype=str, encoding="utf-8")


class DataLoader:
    def __init__(
        self,
        workbook_path: Path = WORKBOOK_PATH,
        followup_path: Path = FOLLOWUP_PATH,
    ):
        self.workbook_path = workbook_path
        self.followup_path = followup_path

    def load(self) -> DataBundle:
        excel = ExcelLoader(self.workbook_path).load()
        auditor = WorkbookAuditor(self.workbook_path)
        return DataBundle(
            responses=excel["responses"],
            scoring=excel["scoring"],
            summary=excel["summary"],
            sheet3=excel["sheet3"],
            final=excel["final"],
            followup=FollowupLoader(self.followup_path).load(),
            formula_audit=auditor.formula_audit(),
            sheet_meta=auditor.sheet_meta(),
            source_paths={
                "workbook": self.workbook_path,
                "followup": self.followup_path,
            },
        )
