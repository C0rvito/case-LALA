from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from matplotlib.patches import Patch, Rectangle
from matplotlib.text import Text

from .config import (
    ADOPTION_STATUS_COLORS,
    ADOPTION_STATUS_LABELS,
    ADOPTION_STATUS_ORDER,
    FIGURE_DIR,
    FIGURE_DPI,
    FIGURE_MANIFEST_PATH,
    FIGURE_QA_PATH,
    FOLLOWUP_STAGE_COLORS,
    FOLLOWUP_STAGE_LABELS,
    ISSUE_CATEGORY_COLORS,
    MIN_FONT_SIZE,
    PALETTE,
    SHEET_COLORS,
    STAGE_LABELS,
)


def _wrap(value: Any, width: int) -> str:
    return textwrap.fill(str(value), width=width, break_long_words=False)


def _short_status(canonical: str) -> str:
    return {
        "approved": "Approved",
        "approved_reserved": "Reserved",
        "waitlist": "Waitlist",
        "list_b": "List B",
        "rejected": "Rejected",
        "reuse": "Reuse",
        "visit": "Visit",
        "unknown": "—",
    }.get(canonical, "—")


class HearthwayTheme:
    @classmethod
    def apply(cls) -> None:
        sns.set_theme(style="whitegrid", context="notebook")
        plt.rcParams.update(
            {
                "font.family": "DejaVu Sans",
                "font.size": 10,
                "axes.titlesize": 11,
                "axes.labelsize": 10,
                "axes.edgecolor": "#B8C1CC",
                "axes.linewidth": 0.8,
                "axes.labelcolor": PALETTE["ink"],
                "axes.titlecolor": PALETTE["ink"],
                "xtick.color": PALETTE["muted"],
                "ytick.color": PALETTE["muted"],
                "xtick.labelsize": 9,
                "ytick.labelsize": 9,
                "text.color": PALETTE["ink"],
                "legend.fontsize": 9,
                "legend.title_fontsize": 9,
                "grid.color": "#E5E7EB",
                "grid.linewidth": 0.7,
                "figure.facecolor": "white",
                "axes.facecolor": "white",
                "savefig.facecolor": "white",
                "savefig.dpi": FIGURE_DPI,
                "figure.dpi": 120,
            }
        )


@dataclass
class FigureSpec:
    fig_id: str
    stage: str
    filename: str
    title: str
    subtitle: str
    question: str
    source: str
    n: str
    denominator: str
    unit: str
    chart_type: str
    checks: dict[str, Any] = field(default_factory=dict)
    interpretation: str = ""
    caveat: str = ""
    svg: bool = False


class FigureValidator:
    def __init__(self, theme=HearthwayTheme):
        self.theme = theme

    def preflight(self, fig: plt.Figure, spec: FigureSpec) -> list[str]:
        warnings: list[str] = []
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        fig_bbox = fig.bbox
        texts: list[tuple[str, Any]] = []
        for text in fig.findobj(Text):
            if not text.get_visible():
                continue
            value = text.get_text()
            if not value or not str(value).strip():
                continue
            try:
                bbox = text.get_window_extent(renderer=renderer)
            except Exception:
                continue
            if bbox.width <= 0 or bbox.height <= 0:
                continue
            texts.append((str(value), bbox))
            if (
                bbox.x0 < fig_bbox.x0 - 1
                or bbox.y0 < fig_bbox.y0 - 1
                or bbox.x1 > fig_bbox.x1 + 1
                or bbox.y1 > fig_bbox.y1 + 1
            ):
                warnings.append(f"Text outside figure: {value[:70]!r}")
            if text.get_fontsize() < MIN_FONT_SIZE - 0.1:
                warnings.append(
                    f"Font below {MIN_FONT_SIZE} pt in {value[:50]!r} "
                    f"({text.get_fontsize():.1f} pt)"
                )
        for index, (value_a, bbox_a) in enumerate(texts):
            for value_b, bbox_b in texts[index + 1 :]:
                x_overlap = max(0, min(bbox_a.x1, bbox_b.x1) - max(bbox_a.x0, bbox_b.x0))
                y_overlap = max(0, min(bbox_a.y1, bbox_b.y1) - max(bbox_a.y0, bbox_b.y0))
                if x_overlap * y_overlap > 6:
                    warnings.append(
                        f"Text overlap: {value_a[:35]!r} / {value_b[:35]!r}"
                    )
        for legend in list(fig.legends) + [
            ax.get_legend() for ax in fig.axes if ax.get_legend() is not None
        ]:
            if legend is None:
                continue
            bbox = legend.get_window_extent(renderer=renderer)
            if (
                bbox.x0 < fig_bbox.x0 - 1
                or bbox.y0 < fig_bbox.y0 - 1
                or bbox.x1 > fig_bbox.x1 + 1
                or bbox.y1 > fig_bbox.y1 + 1
            ):
                warnings.append("Legend outside figure")
        for ax in fig.axes:
            max_categories = spec.checks.get("max_categories")
            if max_categories is not None:
                count = len(ax.get_yticklabels())
                if count > max_categories:
                    warnings.append(
                        f"{count} categories on y-axis; limit {max_categories}"
                    )
            if spec.checks.get("zero_baseline"):
                for container in ax.containers:
                    orientation = getattr(container, "orientation", None)
                    if orientation == "horizontal":
                        if ax.get_xlim()[0] > 0.0001:
                            warnings.append("Horizontal bars without zero baseline")
                    elif orientation == "vertical":
                        if ax.get_ylim()[0] > 0.0001:
                            warnings.append("Vertical bars without zero baseline")
            if spec.checks.get("percent"):
                low, high = ax.get_ylim()
                if low < -0.01 or high > 100.01:
                    warnings.append("Percentage axis outside 0–100")
        return warnings

    def postflight(self, path: Path, spec: FigureSpec) -> list[str]:
        warnings: list[str] = []
        image = mpimg.imread(path)
        height, width = image.shape[:2]
        if width < 1000 or height < 600:
            warnings.append(f"Small image: {width}x{height}px")
        return warnings


class FigureExporter:
    def __init__(
        self,
        figure_dir: Path = FIGURE_DIR,
        manifest_path: Path = FIGURE_MANIFEST_PATH,
        qa_path: Path = FIGURE_QA_PATH,
    ):
        self.figure_dir = figure_dir
        self.manifest_path = manifest_path
        self.qa_path = qa_path
        self.manifest: list[dict] = []
        self.qa: list[dict] = []
        self.validator = FigureValidator()

    def export(self, fig: plt.Figure, spec: FigureSpec) -> dict:
        stage_dir = self.figure_dir / spec.stage
        stage_dir.mkdir(parents=True, exist_ok=True)
        path = stage_dir / f"{spec.filename}.png"
        warnings = self.validator.preflight(fig, spec)
        fig.savefig(
            path,
            dpi=FIGURE_DPI,
            bbox_inches="tight",
            pad_inches=0.12,
            facecolor="white",
        )
        if spec.svg:
            fig.savefig(
                stage_dir / f"{spec.filename}.svg",
                bbox_inches="tight",
                pad_inches=0.12,
                facecolor="white",
            )
        warnings.extend(self.validator.postflight(path, spec))
        image = mpimg.imread(path)
        height, width = image.shape[:2]
        status = "pass" if not warnings else "review"
        row = {
            "figure_id": spec.fig_id,
            "stage": spec.stage,
            "stage_label": STAGE_LABELS.get(spec.stage, spec.stage),
            "filename": spec.filename,
            "path": str(path.relative_to(self.figure_dir.parent)),
            "title": spec.title,
            "question": spec.question,
            "chart_type": spec.chart_type,
            "n": spec.n,
            "denominator": spec.denominator,
            "unit": spec.unit,
            "source": spec.source,
            "qa_status": status,
            "qa_warnings": " | ".join(warnings),
            "width_px": width,
            "height_px": height,
            "interpretation": spec.interpretation,
            "caveat": spec.caveat,
        }
        self.manifest.append(row)
        self.qa.append(
            {
                "figure_id": spec.fig_id,
                "filename": spec.filename,
                "status": status,
                "warnings": len(warnings),
                "warning_detail": " | ".join(warnings),
                "width_px": width,
                "height_px": height,
                "dpi": FIGURE_DPI,
            }
        )
        plt.close(fig)
        return row

    def write_manifest(self) -> None:
        self.figure_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(self.manifest).to_csv(self.manifest_path, index=False)
        self.qa_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(self.qa).to_csv(self.qa_path, index=False)


class ChartFactory:
    def __init__(self, exporter: FigureExporter):
        self.exporter = exporter
        HearthwayTheme.apply()

    def _figure(
        self, figsize: tuple[float, float], right: float = 0.96
    ) -> tuple[plt.Figure, plt.Axes]:
        fig, ax = plt.subplots(figsize=figsize, layout="constrained")
        fig.get_layout_engine().set(rect=(0.02, 0.065, right, 0.80))
        return fig, ax

    def _multi_figure(
        self,
        figsize: tuple[float, float],
        rows: int,
        cols: int,
        right: float = 0.96,
    ) -> tuple[plt.Figure, np.ndarray]:
        fig, axes = plt.subplots(
            rows, cols, figsize=figsize, layout="constrained"
        )
        fig.get_layout_engine().set(rect=(0.02, 0.065, right, 0.80))
        return fig, axes

    def _frame(self, fig: plt.Figure, spec: FigureSpec) -> None:
        title_lines = textwrap.wrap(spec.title, width=92, break_long_words=False)
        title = "\n".join(title_lines)
        fig.text(
            0.018,
            0.985,
            title,
            ha="left",
            va="top",
            fontsize=15,
            fontweight="bold",
            color=PALETTE["ink"],
        )
        title_size = 15
        title_height = title_size / (fig.get_size_inches()[1] * 72)
        subtitle_y = 0.985 - title_height * len(title_lines) - 0.012
        fig.text(
            0.018,
            subtitle_y,
            _wrap(spec.subtitle, 132),
            ha="left",
            va="top",
            fontsize=10,
            color=PALETTE["muted"],
        )
        footer = (
            f"Source: {spec.source}  |  n={spec.n}  |  Denominator: {spec.denominator}  "
            f"|  Unit: {spec.unit}"
        )
        footer_width = min(170, max(90, int(fig.get_size_inches()[0] * 14.0)))
        fig.text(
            0.018,
            0.012,
            _wrap(footer, footer_width),
            ha="left",
            va="bottom",
            fontsize=9,
            color=PALETTE["muted"],
        )

    def _clean(self, ax: plt.Axes, grid_axis: str = "x") -> None:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis=grid_axis, color="#E5E7EB", linewidth=0.7)
        ax.set_axisbelow(True)

    def _outside_legend(
        self,
        fig: plt.Figure,
        handles: list,
        labels: list[str],
        title: str | None = None,
    ) -> None:
        fig.legend(
            handles,
            labels,
            loc="center left",
            bbox_to_anchor=(0.805, 0.52),
            frameon=False,
            title=title,
            handlelength=1.2,
            borderaxespad=0,
        )

    def completeness(
        self, missingness: pd.DataFrame, complete_note: str
    ) -> dict:
        frame = missingness.copy()
        source_order = ["Responses", "Scoring", "Summary", "Sheet3", "final", "Follow-up"]
        frame["source_order"] = frame["source"].map(
            {source: index for index, source in enumerate(source_order)}
        ).fillna(99)
        frame = frame.sort_values(
            ["source_order", "missing_pct"], ascending=[True, True]
        )
        height = max(5.8, 2.5 + 0.255 * len(frame))
        fig, ax = self._figure((13.2, height), right=0.78)
        y = np.arange(len(frame))
        colors = [SHEET_COLORS.get(source, PALETTE["grey"]) for source in frame["source"]]
        ax.barh(
            y,
            frame["missing_pct"],
            color=colors,
            height=0.72,
            edgecolor="white",
            linewidth=0.8,
        )
        ax.set_yticks(y)
        ax.set_yticklabels(frame["field_label"], fontsize=9)
        ax.invert_yaxis()
        ax.set_xlim(0, min(100, max(10, np.ceil(frame["missing_pct"].max() / 10) * 10 + 10)))
        ax.set_xlabel("Missing cells (%)")
        for position, (_, row) in zip(y, frame.iterrows()):
            ax.text(
                row["missing_pct"] + 0.7,
                position,
                f"{int(row['missing'])} ({row['missing_pct']:.0f}%)",
                va="center",
                fontsize=9,
                color=PALETTE["ink"],
            )
        self._clean(ax, "x")
        handles = [
            Patch(facecolor=SHEET_COLORS[source], label=source)
            for source in source_order
            if source in set(frame["source"])
        ]
        self._outside_legend(fig, handles, [handle.get_label() for handle in handles])
        spec = FigureSpec(
            fig_id="F01",
            stage="estrutural",
            filename="estrutural_01_completude_campos",
            title="Fields with missing data by source table",
            subtitle=(
                "Each bar is a field with at least one empty cell. "
                f"{complete_note}"
            ),
            question="Where are the gaps, and which fields are critical?",
            source="03_team_a_adoptions_spring_2026.xlsx; 04_team_b_followup_animals.csv",
            n=f"{len(frame)} fields with missing data",
            denominator="fields with at least one empty cell",
            unit="% of source-table rows",
            chart_type="barras horizontais",
            checks={"zero_baseline": True, "max_categories": 40},
            interpretation=(
                "Ref, comments and follow-up are the emptiest fields; "
                "missingness is mostly structural, not random."
            ),
            caveat=(
                "Fields that are 100% complete are not shown; "
                "Table T03 contains the full profile."
            ),
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)

    def formats(self, formats: pd.DataFrame) -> dict:
        fields = list(dict.fromkeys(formats["field"].tolist()))
        fig, axes = self._multi_figure((13.2, 8.6), 2, 2, right=0.96)
        for ax, field_name in zip(axes.ravel(), fields):
            subset = formats[formats["field"] == field_name].copy()
            subset = subset.sort_values("count", ascending=True)
            y = np.arange(len(subset))
            colors = []
            for value in subset["value"]:
                lower = str(value).casefold()
                if "missing" in lower or "(blank)" in lower:
                    colors.append(PALETTE["light_grey"])
                elif "error" in lower:
                    colors.append(PALETTE["red"])
                elif "placeholder" in lower:
                    colors.append(PALETTE["amber"])
                else:
                    colors.append(PALETTE["primary"])
            ax.barh(
                y,
                subset["count"],
                color=colors,
                height=0.7,
                edgecolor="white",
                linewidth=0.8,
            )
            ax.set_yticks(y)
            ax.set_yticklabels(subset["value"], fontsize=9)
            ax.set_xlim(0, max(1, subset["count"].max() * 1.35))
            ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=5, prune="both"))
            ax.set_xlabel("Records")
            total = int(subset["count"].sum())
            ax.set_title(f"{field_name}  ·  n={total}", loc="left", fontsize=11)
            for position, (_, row) in zip(y, subset.iterrows()):
                ax.text(
                    row["count"] + max(0.3, subset["count"].max() * 0.02),
                    position,
                    f"{int(row['count'])} ({row['pct']:.0f}%)",
                    va="center",
                    fontsize=9,
                    color=PALETTE["ink"],
                )
            self._clean(ax, "x")
        for ax in axes.ravel()[len(fields) :]:
            ax.axis("off")
        spec = FigureSpec(
            fig_id="F02",
            stage="estrutural",
            filename="estrutural_02_formatos_contacto_identidade",
            title="Coexisting formats in contact, date and identity",
            subtitle=(
                "Phone, date of birth and identifier do not have a single format; "
                "each panel uses its own n."
            ),
            question="Which formats coexist in these key fields?",
            source="Responses and Follow-up; values after classification, original unchanged",
            n="4 panels",
            denominator="rows in each source table",
            unit="records",
            chart_type="horizontal bars in small multiples",
            checks={"zero_baseline": True},
            interpretation=(
                "Phone appears in five formats; dates mix dd/mm, ISO, "
                "text and Excel serial; the identifier mixes four types."
            ),
            caveat="Categories describe the observed value, not a data correction.",
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)

    def timeline(self, time_series: pd.DataFrame) -> dict:
        fig, ax = self._figure((12.6, 6.0), right=0.78)
        x = pd.to_datetime(time_series["week_start"])
        bottom = np.zeros(len(time_series))
        for status in ADOPTION_STATUS_ORDER:
            if status not in time_series.columns:
                continue
            values = time_series[status].to_numpy(dtype=float)
            if values.sum() == 0:
                continue
            ax.bar(
                x,
                values,
                bottom=bottom,
                width=5.6,
                color=ADOPTION_STATUS_COLORS[status],
                label=ADOPTION_STATUS_LABELS[status],
                edgecolor="white",
                linewidth=0.8,
            )
            bottom += values
        for position, total in zip(x, time_series["total"]):
            ax.text(
                position,
                total + 0.25,
                f"{int(total)}",
                ha="center",
                va="bottom",
                fontsize=9,
                color=PALETTE["ink"],
                fontweight="bold",
            )
        ax.axvline(
            pd.Timestamp("2026-04-10"),
            color=PALETTE["red"],
            linestyle="--",
            linewidth=1.4,
        )
        ax.text(
            pd.Timestamp("2026-04-10"),
            max(time_series["total"]) + 1.5,
            "Deadline 10/04",
            color=PALETTE["red"],
            fontsize=9,
            ha="center",
        )
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=7))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
        ax.set_xlabel("Application week")
        ax.set_ylabel("Applications")
        ax.set_ylim(0, max(time_series["total"]) + 2.4)
        self._clean(ax, "y")
        handles = [
            Patch(
                facecolor=ADOPTION_STATUS_COLORS[status],
                label=ADOPTION_STATUS_LABELS[status],
            )
            for status in ADOPTION_STATUS_ORDER
            if status in time_series.columns and time_series[status].sum() > 0
        ]
        self._outside_legend(
            fig, handles, [handle.get_label() for handle in handles]
        )
        spec = FigureSpec(
            fig_id="F03",
            stage="estrutural",
            filename="estrutural_03_candidaturas_tempo",
            title="Applications by week and status",
            subtitle=(
                "The campaign is concentrated in March; the final week includes the "
                "10/04/2026 deadline. Test rows excluded."
            ),
            question="How are applications distributed over time?",
            source="Responses; Timestamp field",
            n="24 real applications",
            denominator="real applications (excludes 2 test rows)",
            unit="applications",
            chart_type="stacked bars by week",
            checks={"zero_baseline": True, "max_categories": 8},
            interpretation=(
                "Volume falls over the campaign; the final week has only "
                "three applications and includes the deadline."
            ),
            caveat="The week is a calendar convention, not an operational batch.",
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)

    def status_variants(self, variants: pd.DataFrame) -> dict:
        frame = variants.copy()
        height = max(5.5, 2.2 + 0.34 * len(frame))
        fig, ax = self._figure((12.8, height), right=0.78)
        y = np.arange(len(frame))
        colors = [
            ADOPTION_STATUS_COLORS.get(canonical, PALETTE["light_grey"])
            for canonical in frame["canonical"]
        ]
        ax.barh(
            y,
            frame["count"],
            color=colors,
            height=0.7,
            edgecolor="white",
            linewidth=0.8,
        )
        ax.set_yticks(y)
        ax.set_yticklabels(frame["raw_value"], fontsize=9)
        ax.invert_yaxis()
        ax.set_xlim(0, frame["count"].max() * 1.55)
        ax.set_xlabel("Applications")
        for position, (_, row) in zip(y, frame.iterrows()):
            ax.text(
                row["count"] + 0.15,
                position,
                f"{int(row['count'])} ({row['pct']:.0f}%)",
                va="center",
                fontsize=9,
                color=PALETTE["ink"],
            )
        self._clean(ax, "x")
        present = [
            canonical
            for canonical in ADOPTION_STATUS_ORDER
            if canonical in set(frame["canonical"])
        ]
        handles = [
            Patch(
                facecolor=ADOPTION_STATUS_COLORS[canonical],
                label=ADOPTION_STATUS_LABELS[canonical],
            )
            for canonical in present
        ]
        self._outside_legend(
            fig, handles, [handle.get_label() for handle in handles], "Canonical status"
        )
        spec = FigureSpec(
            fig_id="F04",
            stage="qualidade",
            filename="qualidade_01_variantes_estado",
            title="13 raw status values for 8 canonical statuses",
            subtitle=(
                "The same status appears with different capitalisation, spacing, typos and sub-statuses; "
                "'(blank)' includes the test rows and 1027."
            ),
            question="Which status variants exist, and how many records do they cover?",
            source="Responses; Status field",
            n="26 rows",
            denominator="26 source rows",
            unit="applications",
            chart_type="horizontal bars coloured by canonical status",
            checks={"zero_baseline": True, "max_categories": 20},
            interpretation=(
                "There are 10 canonical approvals, but the Summary formula counts 9; "
                "List B has three variants and only one is caught by the formula."
            ),
            caveat="Colour groups meaning; the y label preserves the original spelling.",
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)

    def presence(self, reconciliation: pd.DataFrame) -> dict:
        frame = reconciliation.copy()
        stages = [
            ("Responses", "in_responses"),
            ("Scoring", "in_scoring"),
            ("final", "in_final"),
            ("Follow-up", "followup_candidates"),
        ]
        height = max(6.5, 2.6 + 0.27 * len(frame))
        fig, ax = self._figure((10.8, height), right=0.78)
        y = np.arange(len(frame))
        for column_index, (stage, field) in enumerate(stages):
            present = (
                frame[field].astype(bool)
                if field != "followup_candidates"
                else frame[field].astype(str).str.len().gt(0)
            )
            ax.scatter(
                np.full(len(frame), column_index),
                y,
                s=110,
                marker="s",
                color=PALETTE["very_light_grey"],
                edgecolor=PALETTE["light_grey"],
                linewidth=0.7,
                zorder=1,
            )
            ax.scatter(
                np.full(int(present.sum()), column_index),
                y[present.to_numpy()],
                s=110,
                marker="s",
                color=SHEET_COLORS[stage],
                edgecolor="white",
                linewidth=0.7,
                zorder=2,
            )
        ax.set_xlim(-0.6, len(stages) - 0.4)
        ax.set_ylim(len(frame) - 0.5, -0.5)
        ax.set_xticks(range(len(stages)))
        ax.set_xticklabels(
            [
                f"{stage}\n(n={int(frame[field].astype(bool).sum() if field != 'followup_candidates' else frame[field].astype(str).str.len().gt(0).sum())})"
                for stage, field in stages
            ],
            fontsize=9,
        )
        ax.xaxis.tick_top()
        ax.set_yticks(y)
        labels = [f"{int(row.ID)}  {row['name']}" for _, row in frame.iterrows()]
        ax.set_yticklabels(labels, fontsize=9.0)
        for label, (_, row) in zip(ax.get_yticklabels(), frame.iterrows()):
            if row["status_conflict"]:
                label.set_color(PALETTE["red"])
            elif row["only_in"] == "final":
                label.set_color(PALETTE["blue"])
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(length=0)
        handles = [
            Patch(facecolor=SHEET_COLORS["Responses"], label="Present"),
            Patch(facecolor=PALETTE["very_light_grey"], edgecolor=PALETTE["light_grey"], label="Absent"),
        ]
        self._outside_legend(fig, handles, [handle.get_label() for handle in handles])
        spec = FigureSpec(
            fig_id="F05",
            stage="qualidade",
            filename="qualidade_02_presenca_por_fonte",
            title="Coverage by source and status conflict",
            subtitle=(
                "Each row is an application; the Follow-up column uses the resolved "
                "best ID. Red = raw status difference; blue = final only."
            ),
            question="Which records exist in each source, and where is there a conflict?",
            source="Responses, Scoring, final and Follow-up",
            n="27 IDs / 23 unique people",
            denominator="unique IDs across Responses, Scoring and final",
            unit="applications",
            chart_type="presence matrix",
            checks={"max_categories": 30},
            interpretation=(
                "Some records exist only upstream (1009, 1018, 1023) and one only downstream "
                "(1012). There are six raw status differences: four progressions and two reversals."
            ),
            caveat="The Follow-up column uses the resolved best ID; Sam A. remains ambiguous and is not marked.",
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)

    def dob_dumbbell(self, dob_audit: pd.DataFrame) -> dict:
        frame = dob_audit[dob_audit["mismatch"]].copy().sort_values("ID")
        height = max(5.2, 2.2 + 0.38 * len(frame))
        fig, ax = self._figure((12.6, height), right=0.96)
        y = np.arange(len(frame))
        expected = pd.to_datetime(frame["expected_dd_mm"])
        stored = pd.to_datetime(frame["dob_clean"])
        for position, (expected_date, stored_date) in enumerate(zip(expected, stored)):
            ax.plot(
                [expected_date, stored_date],
                [position, position],
                color=PALETTE["light_grey"],
                linewidth=3,
                zorder=1,
            )
        ax.scatter(expected, y, color=PALETTE["teal"], s=55, zorder=3, label="Expected under dd/mm")
        ax.scatter(stored, y, color=PALETTE["red"], s=55, zorder=3, label="Value in dob_clean")
        ax.set_yticks(y)
        ax.set_yticklabels(
            [f"{int(row.ID)}  {row.raw_dob}" for _, row in frame.iterrows()],
            fontsize=9,
        )
        ax.invert_yaxis()
        ax.set_xlabel("Date of birth")
        ax.set_xticks(
            [pd.Timestamp(f"{year}-01-01") for year in range(1970, 2000, 5)]
        )
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.tick_params(axis="x", labelrotation=0)
        ax.set_xlim(expected.min() - pd.Timedelta(days=365), stored.max() + pd.Timedelta(days=365))
        self._clean(ax, "x")
        ax.legend(loc="lower right", frameon=False)
        spec = FigureSpec(
            fig_id="F06",
            stage="qualidade",
            filename="qualidade_03_dob_parse",
            title="The date parser differs from dd/mm/yyyy in 10 records",
            subtitle=(
                "The form asks for dd/mm/yyyy; dob_clean used mm/dd for ambiguous values. "
                "For 1016, the duplicate 1023 confirms dob_clean; the other nine still need an audit."
            ),
            question="Where was the date of birth misinterpreted?",
            source="Responses; Date of birth vs dob_clean",
            n="10 mismatching records",
            denominator="26 date-of-birth records",
            unit="dates",
            chart_type="dumbbell plot",
            checks={},
            interpretation=(
                "Ten raw dates differ from dd/mm/yyyy. Only 1016 is independently validated; "
                "using DOB as an identity key still produces false negatives and positives."
            ),
            caveat="The dd/mm/yyyy rule is the form's declared format, not proof of the correct date.",
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)

    def linkage_evidence(self, evidence: pd.DataFrame) -> dict:
        frame = evidence.copy()
        columns = [
            ("Exact\nphone", "phone_exact"),
            ("Name +\ninitial", "name_match"),
            ("Specific\nanimal", "animal_match"),
            ("No\ncandidate", "no_candidate"),
        ]
        frame["no_candidate"] = frame["candidate_count"].eq(0)
        height = max(5.4, 2.2 + 0.33 * len(frame))
        fig, ax = self._figure((10.2, height), right=0.93)
        y = np.arange(len(frame))
        colors = {
            "phone_exact": PALETTE["primary"],
            "name_match": PALETTE["teal"],
            "animal_match": PALETTE["amber"],
            "no_candidate": PALETTE["red"],
        }
        for column_index, (_, field) in enumerate(columns):
            present = frame[field].astype(bool)
            ax.scatter(
                np.full(len(frame), column_index),
                y,
                s=120,
                marker="o",
                color=PALETTE["very_light_grey"],
                edgecolor=PALETTE["light_grey"],
                linewidth=0.7,
                zorder=1,
            )
            ax.scatter(
                np.full(int(present.sum()), column_index),
                y[present.to_numpy()],
                s=120,
                marker="o",
                color=colors[field],
                edgecolor="white",
                linewidth=0.7,
                zorder=2,
            )
        ax.set_xlim(-0.6, len(columns) - 0.4)
        ax.set_ylim(len(frame) - 0.5, -0.5)
        ax.set_xticks(range(len(columns)))
        ax.set_xticklabels([label for label, _ in columns], fontsize=9)
        ax.xaxis.tick_top()
        ax.set_yticks(y)
        ax.set_yticklabels(frame["adopter"], fontsize=9)
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(length=0)
        spec = FigureSpec(
            fig_id="F07",
            stage="semantica",
            filename="semantica_01_evidencia_linkage",
            title="What evidence links Follow-up to Adoptions?",
            subtitle=(
                "Only 2 of 14 adopters have an exact phone; 11 have name + initial. "
                "Deterministic rules resolve eight more, one remains ambiguous and three have no candidate."
            ),
            question="What evidence exists to link the two teams?",
            source="Responses and Follow-up; normalised phone and abbreviated name",
            n="14 Follow-up adopters",
            denominator="14 unique adopters",
            unit="adopters",
            chart_type="evidence matrix",
            checks={"max_categories": 20},
            interpretation=(
                "Phone is rare and insufficient; name+initial is available for 11, "
                "but is rarely unique on its own."
            ),
            caveat="A specific animal is weak evidence: animal names repeat across campaigns.",
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)

    def linkage_candidates(self, pairs: pd.DataFrame) -> dict:
        frame = pairs[pairs["score"] >= 25].copy()
        frame = frame.sort_values(
            ["adopter_b", "score", "candidate_id"], ascending=[True, False, True]
        )
        frame["rank_in_adopter"] = frame.groupby("adopter_b").cumcount() + 1
        frame = frame[frame["rank_in_adopter"] <= 3].reset_index(drop=True)
        frame["label"] = (
            frame["adopter_b"]
            + " → "
            + frame["candidate_id"].astype(int).astype(str)
            + " "
            + frame["candidate_name"]
        )
        height = max(5.4, 2.2 + 0.34 * len(frame))
        fig, ax = self._figure((12.8, height), right=0.78)
        y = np.arange(len(frame))
        for position, (_, row) in enumerate(frame.iterrows()):
            ax.hlines(
                position,
                0,
                row["score"],
                color=PALETTE["light_grey"],
                linewidth=2.2,
                zorder=1,
            )
        confidence_colors = {
            "strong": PALETTE["teal"],
            "medium": PALETTE["blue"],
            "weak": PALETTE["amber"],
        }
        ax.scatter(
            frame["score"],
            y,
            s=70,
            color=[confidence_colors[item] for item in frame["confidence"]],
            edgecolor="white",
            linewidth=0.7,
            zorder=3,
        )
        ax.set_yticks(y)
        ax.set_yticklabels(frame["label"], fontsize=9.0)
        ax.invert_yaxis()
        ax.set_xlim(0, 105)
        ax.set_xlabel("Linkage score (0–100)")
        ax.axvline(45, color=PALETTE["grey"], linestyle=":", linewidth=1)
        ax.axvline(70, color=PALETTE["grey"], linestyle="--", linewidth=1)
        ax.text(46, -1.0, "medium", fontsize=9, color=PALETTE["muted"])
        ax.text(71, -1.0, "strong", fontsize=9, color=PALETTE["muted"])
        for position, (_, row) in enumerate(frame.iterrows()):
            ax.text(
                row["score"] + 1.5,
                position,
                f"{int(row['score'])} · {row['evidence']}",
                va="center",
                fontsize=9.0,
                color=PALETTE["ink"],
            )
        self._clean(ax, "x")
        handles = [
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=color,
                markersize=8,
                label=label,
            )
            for label, color in confidence_colors.items()
            if label in set(frame["confidence"])
        ]
        self._outside_legend(
            fig,
            handles,
            [handle.get_label() for handle in handles],
            "Evidence strength",
        )
        spec = FigureSpec(
            fig_id="F08",
            stage="semantica",
            filename="semantica_02_candidatos_linkage",
            title="Linkage candidates and ambiguity",
            subtitle=(
                "Top-3 candidates with score ≥25 per adopter. "
                f"{int(frame['confidence'].eq('strong').sum())} strong pairs; "
                f"{int(frame['confidence'].eq('weak').sum())} pairs with weak evidence."
            ),
            question="Who are the candidates, and where is identity ambiguous?",
            source="Responses and Follow-up; deterministic name, phone and animal rules",
            n="14 Follow-up adopters",
            denominator="pairs with score ≥25, top-3 per adopter",
            unit="score 0–100",
            chart_type="horizontal lollipop",
            checks={"zero_baseline": True, "max_categories": 40},
            interpretation=(
                "Isla C. and Joe M. resolve by exact phone; Mark S. resolves to Mark Shaw (1016/1023), "
                "not Mark Singh. Sam A. remains ambiguous; use human review."
            ),
            caveat="Score is a triage heuristic. Resolution uses person clusters and status, not the score alone.",
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)

    def screening_heatmap(self, screening: pd.DataFrame) -> dict:
        frame = screening.sort_values("ID").reset_index(drop=True)
        height = max(7.4, 2.6 + 0.36 * len(frame))
        fig = plt.figure(figsize=(13.4, height), layout="constrained")
        fig.get_layout_engine().set(rect=(0.02, 0.065, 0.96, 0.80))
        grid = fig.add_gridspec(1, 2, width_ratios=[3.1, 2.0])
        ax_scores = fig.add_subplot(grid[0, 0])
        ax_status = fig.add_subplot(grid[0, 1], sharey=ax_scores)
        scores = frame[["call_numeric", "visit_numeric", "fit_numeric"]].to_numpy(dtype=float)
        image = ax_scores.imshow(
            scores, cmap="YlGnBu", vmin=1, vmax=5, aspect="auto"
        )
        ax_scores.set_xticks([0, 1, 2])
        ax_scores.set_xticklabels(["Call", "Visit", "Fit"], fontsize=9)
        ax_scores.set_yticks(np.arange(len(frame)))
        ax_scores.set_yticklabels(
            [f"{int(row.ID)}  {row['name']}" for _, row in frame.iterrows()],
            fontsize=9.0,
        )
        for row_index in range(len(frame)):
            for column_index in range(3):
                value = scores[row_index, column_index]
                label = f"{value:.0f}"
                if (
                    column_index == 1
                    and str(frame.loc[row_index, "visit_note"]).strip()
                ):
                    label += "*"
                ax_scores.text(
                    column_index,
                    row_index,
                    label,
                    ha="center",
                    va="center",
                    fontsize=9,
                    color="white" if value >= 4 else PALETTE["ink"],
                    fontweight="bold" if value >= 4 else "normal",
                )
        ax_scores.set_title("Screening scores", loc="left", fontsize=11)
        ax_scores.set_xticks(np.arange(-0.5, 3, 1), minor=True)
        ax_scores.set_yticks(np.arange(-0.5, len(frame), 1), minor=True)
        ax_scores.grid(which="minor", color="white", linewidth=1.2)
        ax_scores.tick_params(which="minor", length=0)
        ax_scores.tick_params(axis="y", length=0)
        cbar = fig.colorbar(image, ax=ax_scores, fraction=0.035, pad=0.02, ticks=[1, 2, 3, 4, 5])
        cbar.set_label("Score", fontsize=9)
        cbar.ax.tick_params(labelsize=9.0)

        ax_status.set_xlim(-0.5, 1.5)
        ax_status.set_ylim(len(frame) - 0.5, -0.5)
        ax_status.set_xticks([0, 1])
        ax_status.set_xticklabels(["Responses", "final"], fontsize=9)
        ax_status.xaxis.tick_top()
        ax_status.tick_params(axis="y", which="both", left=False, labelleft=False)
        ax_status.grid(False)
        for spine in ax_status.spines.values():
            spine.set_visible(False)
        ax_status.tick_params(length=0)
        for row_index, (_, row) in enumerate(frame.iterrows()):
            values = [
                row["response_status_canon"],
                row["final_status_canon"] if pd.notna(row["final_status_canon"]) else "unknown",
            ]
            for column_index, canonical in enumerate(values):
                color = ADOPTION_STATUS_COLORS.get(canonical, PALETTE["light_grey"])
                rectangle = Rectangle(
                    (column_index - 0.45, row_index - 0.42),
                    0.9,
                    0.84,
                    facecolor=color,
                    edgecolor="white",
                    linewidth=0.8,
                )
                ax_status.add_patch(rectangle)
                text_color = PALETTE["ink"]
                if canonical in {"approved", "rejected", "primary"}:
                    text_color = "white"
                ax_status.text(
                    column_index,
                    row_index,
                    _short_status(canonical),
                    ha="center",
                    va="center",
                    fontsize=9.0,
                    color=text_color,
                )
            if row["conflict"]:
                ax_status.add_patch(
                    Rectangle(
                        (0.55, row_index - 0.44),
                        0.9,
                        0.88,
                        facecolor="none",
                        edgecolor=PALETTE["red"],
                        linewidth=1.8,
                    )
                )
        ax_status.set_title("Status by source", loc="left", fontsize=11)
        spec = FigureSpec(
            fig_id="F09",
            stage="semantica",
            filename="semantica_03_scores_screening",
            title="Screening scores and outcome by application",
            subtitle=(
                "16 applications with scoring; the table on the right shows status in "
                "Responses and final. Red outline = conflict between sources."
            ),
            question="How are Call, Visit and Fit distributed, and how do they relate to outcome?",
            source="Scoring + Responses + final",
            n="16 applications with scoring",
            denominator="24 real applications",
            unit="score 1–5",
            chart_type="heatmap + status table",
            checks={"max_categories": 20},
            interpretation=(
                "High scores appear in approved applications, but also in "
                "waitlisted and rejected ones; outcome is not explained by a single signal."
            ),
            caveat=(
                "Small sample and incomplete follow-up; do not infer causality. "
                "* Visit for 1020 was extracted from the original text."
            ),
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)

    def stage_coverage(self, stage: pd.DataFrame) -> dict:
        frame = stage.copy()
        height = max(4.6, 2.2 + 0.45 * len(frame))
        fig, ax = self._figure((11.4, height), right=0.96)
        y = np.arange(len(frame))
        colors = [PALETTE["primary"]] * len(frame)
        colors[-1] = PALETTE["teal"]
        ax.barh(
            y,
            frame["value"],
            color=colors,
            height=0.68,
            edgecolor="white",
            linewidth=0.8,
        )
        ax.set_yticks(y)
        ax.set_yticklabels(frame["stage"], fontsize=9.5)
        ax.invert_yaxis()
        ax.set_xlim(0, max(frame["value"]) * 1.38)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=6, prune="both"))
        ax.set_xlabel("Records")
        for position, (_, row) in enumerate(frame.iterrows()):
            pct = 100 * row["value"] / row["denominator"] if row["denominator"] else 0
            ax.text(
                row["value"] + 0.35,
                position,
                f"{int(row['value'])} / {int(row['denominator'])}  ({pct:.0f}%)",
                va="center",
                fontsize=9,
                color=PALETTE["ink"],
            )
        self._clean(ax, "x")
        spec = FigureSpec(
            fig_id="F10",
            stage="semantica",
            filename="semantica_04_funil_cobertura",
            title="Coverage of the adoption process",
            subtitle=(
                "Stages are not strictly nested: final includes 1012, "
                "absent from Responses. The denominator changes between rows."
            ),
            question="Where does the funnel lose records?",
            source="Responses, Scoring and final",
            n="24 real applications",
            denominator="24 real; 13 in final",
            unit="records",
            chart_type="horizontal stage bars",
            checks={"zero_baseline": True, "max_categories": 10},
            interpretation=(
                "24 real applications (23 unique people), 16 with scoring, 13 in final and 11 approved; "
                "the funnel loses most records between application and scoring."
            ),
            caveat="Coverage comparison, not a conversion rate between stages.",
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)

    def followup_result(self, summary: pd.DataFrame) -> dict:
        frame = summary.copy().sort_values("total", ascending=True)
        height = max(4.8, 2.2 + 0.42 * len(frame))
        fig, ax = self._figure((11.8, height), right=0.78)
        y = np.arange(len(frame))
        left = np.zeros(len(frame))
        for stage in ["1m", "6m", "none"]:
            values = frame[stage].to_numpy(dtype=float)
            ax.barh(
                y,
                values,
                left=left,
                color=FOLLOWUP_STAGE_COLORS[stage],
                label=FOLLOWUP_STAGE_LABELS[stage],
                height=0.68,
                edgecolor="white",
                linewidth=0.8,
            )
            for position, value in enumerate(values):
                if value > 0:
                    ax.text(
                        left[position] + value / 2,
                        position,
                        f"{int(value)}",
                        ha="center",
                        va="center",
                        fontsize=9,
                        color="white" if stage != "none" else PALETTE["ink"],
                    )
            left += values
        ax.set_yticks(y)
        ax.set_yticklabels(frame["status_label"], fontsize=9)
        ax.invert_yaxis()
        ax.set_xlim(0, frame["total"].max() * 1.55)
        ax.set_xlabel("Follow-up rows")
        for position, (_, row) in enumerate(frame.iterrows()):
            ax.text(
                row["total"] + 0.2,
                position,
                f"{int(row['total'])} · {row['pct_with_followup']:.0f}% with follow-up",
                va="center",
                fontsize=9.0,
                color=PALETTE["ink"],
            )
        self._clean(ax, "x")
        handles = [
            Patch(facecolor=FOLLOWUP_STAGE_COLORS[stage], label=FOLLOWUP_STAGE_LABELS[stage])
            for stage in ["1m", "6m", "none"]
        ]
        self._outside_legend(fig, handles, [handle.get_label() for handle in handles], "Follow-up")
        spec = FigureSpec(
            fig_id="F11",
            stage="semantica",
            filename="semantica_05_followup_resultado",
            title="What Follow-up observes",
            subtitle=(
                "Nine of 16 rows have no 1m/6m follow-up. DOG-0424 is a fallback "
                "reservation, not a duplicate; DOG-0418→0421 is one swap."
            ),
            question="Which follow-up outcomes and stages exist?",
            source="04_team_b_followup_animals.csv",
            n="16 Follow-up rows",
            denominator="15 placement episodes (16 rows minus the swap row)",
            unit="rows",
            chart_type="stacked horizontal bars",
            checks={"zero_baseline": True, "max_categories": 12},
            interpretation=(
                "Only 'Handed over' has 1m/6m follow-up; returns, non-collections and "
                "reservations appear without a contact date."
            ),
            caveat="The list looks current, not a closed cohort; the year is not recorded.",
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)

    def issue_priority(self, issues: pd.DataFrame) -> dict:
        frame = issues.sort_values(
            ["priority_score", "impact", "frequency"], ascending=False
        ).head(12).copy()
        height = max(5.2, 2.2 + 0.42 * len(frame))
        fig, ax = self._figure((13.0, height), right=0.78)
        y = np.arange(len(frame))
        colors = [
            ISSUE_CATEGORY_COLORS.get(category, PALETTE["grey"])
            for category in frame["category"]
        ]
        ax.barh(
            y,
            frame["priority_score"],
            color=colors,
            height=0.68,
            edgecolor="white",
            linewidth=0.8,
        )
        labels = [
            f"{row.issue_id}  {_wrap(row.issue, 52)}"
            for row in frame.itertuples()
        ]
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=9.0)
        ax.invert_yaxis()
        ax.set_xlim(0, frame["priority_score"].max() * 1.42)
        ax.set_xlabel("Priority score")
        for position, (_, row) in enumerate(frame.iterrows()):
            ax.text(
                row["priority_score"] + 0.12,
                position,
                f"freq. {row['frequency']:g}  ·  impact {int(row['impact'])}",
                va="center",
                fontsize=9.0,
                color=PALETTE["ink"],
            )
        self._clean(ax, "x")
        categories = [
            category
            for category in ISSUE_CATEGORY_COLORS
            if category in set(frame["category"])
        ]
        handles = [
            Patch(facecolor=ISSUE_CATEGORY_COLORS[category], label=category)
            for category in categories
        ]
        self._outside_legend(fig, handles, [handle.get_label() for handle in handles], "Category")
        spec = FigureSpec(
            fig_id="F12",
            stage="semantica",
            filename="semantica_06_prioridade_anomalias",
            title="Priority of semantic issues",
            subtitle=(
                f"Top 12 of {len(issues)} issues; score = impact × "
                "(1 + log10(frequency + 1)). The rest are in table T14."
            ),
            question="Which issues have the greatest operational impact?",
            source="EDA issue register (T14)",
            n=f"{len(issues)} issues",
            denominator=f"top 12 of {len(issues)}",
            unit="dimensionless score",
            chart_type="sorted horizontal bars",
            checks={"zero_baseline": True, "max_categories": 15},
            interpretation=(
                "Identity, status conflicts and dates without a year dominate priority; "
                "these are not just 'dirty cells', they are data-model failures."
            ),
            caveat="The score is a prioritisation heuristic, not a risk measure.",
        )
        self._frame(fig, spec)
        return self.exporter.export(fig, spec)
