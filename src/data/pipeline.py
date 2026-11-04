from __future__ import annotations

import hashlib
import json
import sys
from importlib.metadata import version
from pathlib import Path

import pandas as pd

from .config import OUTPUT_DIR, RUN_MANIFEST_PATH
from .io import DataBundle, DataLoader
from .linkage import AdopterLinker, LinkageResult
from .normalize import DataNormalizer, NormalizedBundle
from .profiling import StructuralProfiler
from .report import ReportWriter
from .semantic import AnalysisBuilder, IssueRegister, StatusReconciler
from .tables import TableExporter
from .visuals import ChartFactory, FigureExporter


class EDAPipeline:
    def run(self) -> dict:
        bundle = DataLoader().load()
        normalized = DataNormalizer(bundle).normalize()
        profiler = StructuralProfiler(bundle, normalized)
        linkage = AdopterLinker(
            normalized.responses, normalized.followup, normalized.final
        ).build()
        reconciler = StatusReconciler(normalized, linkage)
        analysis = AnalysisBuilder(normalized, linkage)
        issues = IssueRegister(normalized, linkage, analysis).build()

        missingness = profiler.missingness()
        complete_note = self._complete_note(profiler.column_profile())
        formats = self._format_counts(normalized)
        time_series = analysis.time_series()
        status_variants = analysis.status_variants()
        reconciliation = reconciler.reconciliation()
        dob_audit = profiler.dob_audit()
        screening = analysis.screening_table()
        stage = analysis.stage_coverage()
        followup_summary = analysis.followup_summary()

        tables = self._build_tables(
            bundle=bundle,
            normalized=normalized,
            profiler=profiler,
            linkage=linkage,
            reconciler=reconciler,
            analysis=analysis,
            issues=issues,
            missingness=missingness,
            formats=formats,
            time_series=time_series,
            status_variants=status_variants,
            reconciliation=reconciliation,
        )

        exporter = FigureExporter()
        charts = ChartFactory(exporter)
        figures = [
            charts.completeness(missingness, complete_note),
            charts.formats(formats),
            charts.timeline(time_series),
            charts.status_variants(status_variants),
            charts.presence(reconciliation),
            charts.dob_dumbbell(dob_audit),
            charts.linkage_evidence(linkage.evidence_summary),
            charts.linkage_candidates(linkage.candidate_pairs),
            charts.screening_heatmap(screening),
            charts.stage_coverage(stage),
            charts.followup_result(followup_summary),
            charts.issue_priority(issues),
        ]
        exporter.write_manifest()

        qa_path = exporter.qa_path
        if qa_path.exists():
            tables["T27_figure_qa"] = pd.read_csv(qa_path)
        table_exporter = TableExporter()
        table_exporter.export_csv(tables)
        table_exporter.export_excel(tables)

        manifest = self._run_manifest(bundle, normalized, tables, figures)
        RUN_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        RUN_MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ReportWriter().write(tables, figures, manifest)
        self._print_summary(tables, figures)
        return manifest

    def _build_tables(
        self,
        *,
        bundle: DataBundle,
        normalized: NormalizedBundle,
        profiler: StructuralProfiler,
        linkage: LinkageResult,
        reconciler: StatusReconciler,
        analysis: AnalysisBuilder,
        issues: pd.DataFrame,
        missingness: pd.DataFrame,
        formats: pd.DataFrame,
        time_series: pd.DataFrame,
        status_variants: pd.DataFrame,
        reconciliation: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        return {
            "T01_inventory": profiler.inventory(),
            "T02_column_profile": profiler.column_profile(),
            "T03_missingness": missingness,
            "T04_value_variants": profiler.value_variants(),
            "T05_duplicates": profiler.duplicates(),
            "T06_formula_audit": profiler.formula_audit(),
            "T07_formula_summary": profiler.formula_summary(),
            "T08_dob_audit": profiler.dob_audit(),
            "T09_updated_audit": profiler.updated_audit(),
            "T10_candidate_pairs": linkage.candidate_pairs,
            "T11_adopter_links": linkage.adopter_links,
            "T12_reconciliation": reconciliation,
            "T13_animal_identity": linkage.animal_identity,
            "T14_issue_register": issues,
            "T15_screening_outcomes": analysis.screening_table(),
            "T16_followup_summary": analysis.followup_summary(),
            "T17_kpis": analysis.kpis(),
            "T18_summary_reconciliation": analysis.summary_reconciliation(),
            "T19_status_crosswalk": reconciler.crosswalk(),
            "T20_stage_coverage": analysis.stage_coverage(),
            "T21_format_counts": formats,
            "T22_time_series": time_series,
            "T23_status_variants": status_variants,
            "T24_evidence_summary": linkage.evidence_summary,
            "T25_animal_matches": linkage.animal_matches,
            "T26_screening_by_outcome": analysis.screening_outcome_summary(),
        }

    @staticmethod
    def _format_counts(normalized: NormalizedBundle) -> pd.DataFrame:
        rows: list[dict] = []

        def add(field: str, series: pd.Series) -> None:
            total = len(series)
            counts = series.astype(object).value_counts(dropna=False)
            for value, count in counts.items():
                label = "(blank)" if pd.isna(value) else str(value)
                rows.append(
                    {
                        "field": field,
                        "value": label,
                        "count": int(count),
                        "pct": round(100 * int(count) / total, 1) if total else 0.0,
                    }
                )

        add("Phone — Adoptions", normalized.responses["phone_format"])
        add("Phone — Follow-up", normalized.followup["phone_format"])
        add("Date of birth — Adoptions", normalized.responses["dob_format"])
        add("Identifier — Adoptions", normalized.responses["identity_type"])
        return pd.DataFrame(
            rows, columns=["field", "value", "count", "pct"]
        )

    @staticmethod
    def _complete_note(profile: pd.DataFrame) -> str:
        order = ["Responses", "Scoring", "Summary", "Sheet3", "final", "Follow-up"]
        parts: list[str] = []
        for source in order:
            group = profile[profile["source"] == source]
            if group.empty:
                continue
            complete = int(group["missing"].eq(0).sum())
            parts.append(f"{source} {complete}/{len(group)}")
        return "Fields 100% complete: " + ", ".join(parts) + "."

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _run_manifest(
        self,
        bundle: DataBundle,
        normalized: NormalizedBundle,
        tables: dict[str, pd.DataFrame],
        figures: list[dict],
    ) -> dict:
        source_paths = {
            "workbook": bundle.source_paths["workbook"],
            "followup": bundle.source_paths["followup"],
        }
        source_hashes = {
            name: self._sha256(path) for name, path in source_paths.items()
        }
        return {
            "project": "Hearthway Rehoming Network — Spring 2026 EDA",
            "command": "uv run python -m data",
            "python": sys.version.split()[0],
            "packages": {
                "pandas": version("pandas"),
                "openpyxl": version("openpyxl"),
                "matplotlib": version("matplotlib"),
                "seaborn": version("seaborn"),
            },
            "source_sha256": source_hashes,
            "counts": {
                "responses": len(bundle.responses),
                "scoring": len(bundle.scoring),
                "final": len(bundle.final),
                "followup": len(bundle.followup),
                "real_applications": int((~normalized.responses["is_test"]).sum()),
            },
            "tables": {
                name: int(len(frame)) for name, frame in tables.items()
            },
            "figures": [
                {
                    "figure_id": row["figure_id"],
                    "path": row["path"],
                    "qa_status": row["qa_status"],
                    "qa_warnings": row["qa_warnings"],
                }
                for row in figures
            ],
            "figure_count": len(figures),
            "table_count": len(tables),
            "output_dir": str(OUTPUT_DIR.relative_to(OUTPUT_DIR.parent)),
        }

    @staticmethod
    def _print_summary(
        tables: dict[str, pd.DataFrame], figures: list[dict]
    ) -> None:
        passed = sum(1 for row in figures if row["qa_status"] == "pass")
        print(
            f"EDA complete: {len(figures)} figures ({passed} pass), "
            f"{len(tables)} tables."
        )
        print(f"Report: {OUTPUT_DIR / 'eda_report.md'}")
        print(f"Tables: {OUTPUT_DIR / 'tables' / 'eda_tables.xlsx'}")
        print(f"Manifest: {RUN_MANIFEST_PATH}")
