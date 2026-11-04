from __future__ import annotations

from typing import Iterable

import pandas as pd

from .config import ADOPTION_STATUS_LABELS, FOLLOWUP_STATUS_LABELS
from .io import DataBundle
from .normalize import NormalizedBundle, _as_text


class StructuralProfiler:
    def __init__(self, bundle: DataBundle, normalized: NormalizedBundle):
        self.bundle = bundle
        self.normalized = normalized

    def inventory(self) -> pd.DataFrame:
        frames = {
            "Responses": self.bundle.responses,
            "Scoring": self.bundle.scoring,
            "Summary": self.bundle.summary,
            "Sheet3": self.bundle.sheet3,
            "final": self.bundle.final,
            "Follow-up": self.bundle.followup,
        }
        meta = self.bundle.sheet_meta.set_index("sheet")
        rows: list[dict] = []
        for source, frame in frames.items():
            total_cells = int(frame.shape[0] * frame.shape[1])
            missing_cells = int(frame.isna().sum().sum())
            duplicate_rows = int(frame.duplicated().sum())
            formula_cells = (
                int(meta.loc[source, "formula_cells"]) if source in meta.index else 0
            )
            note = ""
            if source == "Responses":
                note = "Two-row header; includes test rows."
            elif source == "Summary":
                note = "Labels and formulas only; values are not cached."
            elif source == "Sheet3":
                note = "Draft sheet with dates and a list of IDs."
            elif source == "Follow-up":
                note = "CSV without application IDs; dates without a year."
            rows.append(
                {
                    "source": source,
                    "rows": int(frame.shape[0]),
                    "columns": int(frame.shape[1]),
                    "cells": total_cells,
                    "missing_cells": missing_cells,
                    "missing_pct": round(100 * missing_cells / total_cells, 1)
                    if total_cells
                    else 0.0,
                    "duplicate_rows": duplicate_rows,
                    "formula_cells": formula_cells,
                    "note": note,
                }
            )
        return pd.DataFrame(rows)

    def column_profile(self) -> pd.DataFrame:
        frames = {
            "Responses": self.bundle.responses,
            "Scoring": self.bundle.scoring,
            "Summary": self.bundle.summary,
            "Sheet3": self.bundle.sheet3,
            "final": self.bundle.final,
            "Follow-up": self.bundle.followup,
        }
        rows: list[dict] = []
        for source, frame in frames.items():
            for position, column in enumerate(frame.columns):
                series = frame[column]
                non_null = int(series.notna().sum())
                missing = int(series.isna().sum())
                values = series.dropna()
                top_value = ""
                top_count = 0
                if not values.empty:
                    counts = values.astype(str).value_counts()
                    top_value = str(counts.index[0])
                    top_count = int(counts.iloc[0])
                example = ""
                if not values.empty:
                    example = str(values.iloc[0])
                label = str(column)
                if isinstance(column, int):
                    label = f"col_{position + 1}"
                rows.append(
                    {
                        "source": source,
                        "column": label,
                        "dtype": str(series.dtype),
                        "non_null": non_null,
                        "missing": missing,
                        "missing_pct": round(100 * missing / len(frame), 1)
                        if len(frame)
                        else 0.0,
                        "unique": int(values.nunique(dropna=True)),
                        "top_value": top_value,
                        "top_count": top_count,
                        "example": example,
                    }
                )
        return pd.DataFrame(rows)

    def missingness(self) -> pd.DataFrame:
        profile = self.column_profile()
        result = profile[profile["missing"] > 0].copy()
        result["field_label"] = result["source"] + " · " + result["column"].astype(str)
        result = result.sort_values(
            ["missing_pct", "missing"], ascending=[True, True]
        ).reset_index(drop=True)
        return result[
            [
                "source",
                "column",
                "field_label",
                "missing",
                "missing_pct",
                "non_null",
            ]
        ]

    def value_variants(self) -> pd.DataFrame:
        rows: list[dict] = []

        def add(
            source: str,
            field: str,
            series: pd.Series,
            canonical: pd.Series | None = None,
            label_map: dict[str, str] | None = None,
        ) -> None:
            total = len(series)
            for value, count in series.astype(object).value_counts(dropna=False).items():
                missing = bool(pd.isna(value))
                raw = "(blank)" if missing else str(value)
                canon = ""
                canon_label = ""
                if canonical is not None:
                    index = series.index[series.astype(object).eq(value)]
                    if len(index):
                        canon = str(canonical.loc[index[0]])
                        if label_map:
                            canon_label = label_map.get(canon, canon)
                rows.append(
                    {
                        "source": source,
                        "field": field,
                        "raw_value": raw,
                        "count": int(count),
                        "pct": round(100 * int(count) / total, 1) if total else 0.0,
                        "canonical": canon,
                        "canonical_label": canon_label,
                    }
                )

        responses = self.normalized.responses
        add(
            "Responses",
            "Status",
            responses["Status"],
            responses["status_canon"],
            ADOPTION_STATUS_LABELS,
        )
        for field in [
            "Town",
            "Home",
            "Animals",
            "How did you hear about us?",
            "Animal",
            "Reviewed",
            "Ref",
            "Adopter no. or passport/licence",
        ]:
            add("Responses", field, responses[field])
        final = self.normalized.final
        add("final", "Status", final["Status"], final["status_canon"], ADOPTION_STATUS_LABELS)
        add("final", "Email sent", final["Email sent"])
        followup = self.normalized.followup
        add(
            "Follow-up",
            "status",
            followup["status"],
            followup["status_canon"],
            FOLLOWUP_STATUS_LABELS,
        )
        add("Follow-up", "followup", followup["followup"])
        add("Follow-up", "animal_swap", followup["animal_swap"])
        add("Follow-up", "updated", followup["updated"])
        add("Follow-up", "species", followup["species"])
        scoring = self.normalized.scoring
        add("Scoring", "Reviewer", scoring["Reviewer"])
        return pd.DataFrame(rows)

    def duplicates(self) -> pd.DataFrame:
        rows: list[dict] = []

        def add_group(
            source: str,
            key_name: str,
            frame: pd.DataFrame,
            key: str | list[str],
            id_columns: Iterable[str],
            note: str = "",
        ) -> None:
            grouped = frame.groupby(key, dropna=False, sort=False)
            for group_key, group in grouped:
                if len(group) < 2:
                    continue
                detail = "; ".join(
                    " | ".join(
                        f"{column}={_as_text(row[column])}"
                        for column in id_columns
                        if column in group.columns
                    )
                    for _, row in group.iterrows()
                )
                rows.append(
                    {
                        "source": source,
                        "key_type": key_name,
                        "key_value": _as_text(group_key)
                        if not isinstance(group_key, tuple)
                        else " / ".join(_as_text(item) for item in group_key),
                        "count": len(group),
                        "detail": detail,
                        "note": note,
                    }
                )

        responses = self.normalized.responses
        add_group("Responses", "Full name", responses, ["First name", "Last name"], ["ID", "Email", "Status"])
        add_group("Responses", "Email", responses, "Email", ["ID", "First name", "Last name"])
        add_group("Responses", "Normalized phone", responses, "phone_norm", ["ID", "First name", "Last name", "Phone"])
        add_group(
            "Responses",
            "Adopter no./document",
            responses,
            "Adopter no. or passport/licence",
            ["ID", "First name", "Last name"],
            "Field mixes adopter number, document and number.",
        )
        add_group("Responses", "Date of birth", responses, "dob_clean", ["ID", "First name", "Last name"])

        scoring = self.normalized.scoring
        add_group("Scoring", "ID", scoring, "ID", ["ID", "Reviewer"])

        final = self.normalized.final
        add_group("final", "Full name", final, "Full name", ["ID", "Status", "Email sent"])

        followup = self.normalized.followup
        add_group("Follow-up", "Animal code", followup, "animal_code", ["animal_code", "adopter", "status"])
        add_group("Follow-up", "Adopter", followup, "adopter", ["animal_code", "adopter", "status"])
        add_group("Follow-up", "Normalized phone", followup, "phone_norm", ["animal_code", "adopter", "followup_phone"])
        return pd.DataFrame(rows)

    def formula_audit(self) -> pd.DataFrame:
        audit = self.bundle.formula_audit.copy()
        return audit.sort_values(["sheet", "cell"]).reset_index(drop=True)

    def formula_summary(self) -> pd.DataFrame:
        audit = self.formula_audit()
        if audit.empty:
            return pd.DataFrame(
                columns=["sheet", "formulas", "ok", "error", "no_cache"]
            )
        formulas = audit[audit["kind"].eq("formula")]
        errors = audit[audit["kind"].eq("error")]
        result = (
            formulas.assign(
                ok=formulas["status"].eq("ok"),
                error=formulas["status"].eq("error"),
                no_cache=formulas["status"].eq("no cached value"),
            )
            .groupby("sheet")[["ok", "error", "no_cache"]]
            .sum()
            .reset_index()
        )
        result["formulas"] = result[["ok", "error", "no_cache"]].sum(axis=1)
        error_counts = (
            errors.groupby("sheet").size().rename("error_cells").reset_index()
        )
        result = result.merge(error_counts, on="sheet", how="outer").fillna(0)
        for column in ["formulas", "ok", "error", "no_cache", "error_cells"]:
            result[column] = result[column].astype(int)
        return result[
            ["sheet", "formulas", "ok", "error", "no_cache", "error_cells"]
        ]

    def dob_audit(self) -> pd.DataFrame:
        audit = self.normalized.dob_audit.copy()
        audit["expected_dd_mm"] = pd.to_datetime(
            audit["expected_dd_mm"], errors="coerce"
        )
        audit["dob_clean"] = pd.to_datetime(audit["dob_clean"], errors="coerce")
        return audit

    def updated_audit(self) -> pd.DataFrame:
        return self.normalized.updated_audit.copy()
