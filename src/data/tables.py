from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .config import TABLE_DIR


class TableExporter:
    def __init__(self, output_dir: Path = TABLE_DIR):
        self.output_dir = output_dir

    def export_csv(self, tables: dict[str, pd.DataFrame]) -> list[Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for name, frame in tables.items():
            path = self.output_dir / f"{name}.csv"
            frame.to_csv(path, index=False, encoding="utf-8-sig")
            paths.append(path)
        return paths

    def export_excel(
        self, tables: dict[str, pd.DataFrame], filename: str = "eda_tables.xlsx"
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / filename
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for name, frame in tables.items():
                sheet_name = name[:31]
                frame.to_excel(writer, sheet_name=sheet_name, index=False)
                worksheet = writer.sheets[sheet_name]
                self._format_sheet(worksheet, frame)
            properties = writer.book.properties
            properties.creator = "Hearthway EDA"
            properties.lastModifiedBy = "Hearthway EDA"
            properties.created = datetime(2026, 1, 1)
            properties.modified = datetime(2026, 1, 1)
        return path

    def _format_sheet(self, worksheet, frame: pd.DataFrame) -> None:
        header_fill = PatternFill("solid", fgColor="0F4C5C")
        header_font = Font(color="FFFFFF", bold=True, size=10)
        body_font = Font(size=10, color="1F2933")
        thin = Side(style="thin", color="D9D9D9")
        border = Border(bottom=thin)
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for column_index, column in enumerate(frame.columns, start=1):
            values = [str(column)] + [
                "" if pd.isna(value) else str(value) for value in frame[column].head(300)
            ]
            width = min(45, max(10, max(len(value) for value in values) + 2))
            worksheet.column_dimensions[get_column_letter(column_index)].width = width
            for row_index in range(2, len(frame) + 2):
                cell = worksheet.cell(row=row_index, column=column_index)
                cell.font = body_font
                cell.border = border
                if len(str(cell.value)) > width:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
        for row_index in range(2, min(len(frame) + 2, 50)):
            worksheet.row_dimensions[row_index].height = 18
