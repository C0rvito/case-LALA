from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from .config import (
    ADOPTION_STATUS_LABELS,
    ADOPTION_STATUS_ORDER,
    FOLLOWUP_STATUS_LABELS,
    FOLLOWUP_STATUS_ORDER,
)
from .linkage import LinkageResult
from .normalize import NormalizedBundle, _as_text


def _base_status(canonical: str) -> str:
    if canonical in {"approved", "approved_reserved"}:
        return "approved"
    return canonical


@dataclass
class SemanticIssue:
    issue_id: str
    category: str
    issue: str
    evidence: str
    frequency: float
    denominator: str
    human_reason: str
    impact: int
    confidence: str
    treatment: str

    @property
    def priority_score(self) -> float:
        return round(self.impact * (1 + math.log10(max(self.frequency, 1) + 1)), 2)


class StatusReconciler:
    MEANINGS = {
        "approved": "Application approved; does not imply handover.",
        "approved_reserved": "Approved and animal reserved; handover not confirmed.",
        "waitlist": "On the waiting list.",
        "list_b": "List B / alternative.",
        "rejected": "Rejected; the reason may be in the free text.",
        "reuse": "Reuse of adopter or animal.",
        "visit": "Visit scheduled/completed; it is a stage, not an outcome.",
        "unknown": "No status recorded.",
        "placed": "Animal handed over; 1- or 6-month follow-up.",
        "reserved": "Animal reserved; handover not confirmed.",
        "not_collected": "Approved, but the adopter did not collect the animal.",
        "returned": "Animal returned.",
        "returned_trial": "Animal returned during the trial.",
        "swapped": "Animal swap; see the code chain.",
        "place_waitlist": "On the waiting list.",
    }

    def __init__(self, normalized: NormalizedBundle, linkage: LinkageResult):
        self.normalized = normalized
        self.linkage = linkage

    def crosswalk(self) -> pd.DataFrame:
        rows: list[dict] = []
        responses = self.normalized.responses
        for raw in responses["Status"].astype(object).value_counts(dropna=False).index:
            missing = bool(pd.isna(raw))
            sample = responses[responses["Status"].astype(object).eq(raw)]
            canonical = sample["status_canon"].iloc[0] if len(sample) else "unknown"
            rows.append(
                {
                    "source": "Adoptions",
                    "raw_value": "(blank)" if missing else str(raw),
                    "canonical": canonical,
                    "canonical_label": ADOPTION_STATUS_LABELS.get(canonical, canonical),
                    "group": sample["status_group"].iloc[0] if len(sample) else "unknown",
                    "meaning": self.MEANINGS.get(canonical, ""),
                }
            )
        final = self.normalized.final
        for raw in final["Status"].astype(object).value_counts(dropna=False).index:
            missing = bool(pd.isna(raw))
            sample = final[final["Status"].astype(object).eq(raw)]
            canonical = sample["status_canon"].iloc[0] if len(sample) else "unknown"
            rows.append(
                {
                    "source": "final",
                    "raw_value": "(blank)" if missing else str(raw),
                    "canonical": canonical,
                    "canonical_label": ADOPTION_STATUS_LABELS.get(canonical, canonical),
                    "group": "final",
                    "meaning": self.MEANINGS.get(canonical, ""),
                }
            )
        followup = self.normalized.followup
        for raw in followup["status"].astype(object).value_counts(dropna=False).index:
            missing = bool(pd.isna(raw))
            sample = followup[followup["status"].astype(object).eq(raw)]
            canonical = sample["status_canon"].iloc[0] if len(sample) else "unknown"
            rows.append(
                {
                    "source": "Follow-up",
                    "raw_value": "(blank)" if missing else str(raw),
                    "canonical": canonical,
                    "canonical_label": FOLLOWUP_STATUS_LABELS.get(canonical, canonical),
                    "group": "follow-up",
                    "meaning": self.MEANINGS.get(canonical, ""),
                }
            )
        return pd.DataFrame(rows).drop_duplicates(
            ["source", "raw_value", "canonical"]
        ).reset_index(drop=True)

    def reconciliation(self) -> pd.DataFrame:
        responses = self.normalized.responses.set_index("ID", drop=False)
        scoring = self.normalized.scoring.set_index("ID", drop=False)
        final = self.normalized.final.set_index("ID", drop=False)
        people = self.linkage.person_map.set_index("ID")
        followup_by_id: dict[int, list[str]] = {}
        for _, row in self.linkage.adopter_links.iterrows():
            if pd.isna(row["best_id"]):
                continue
            candidate_id = int(row["best_id"])
            followup_by_id.setdefault(candidate_id, []).append(
                f"{row['adopter']} ({row['confidence']})"
            )

        ids = sorted(set(responses.index) | set(scoring.index) | set(final.index))
        rows: list[dict] = []
        for record_id in ids:
            in_responses = record_id in responses.index
            in_scoring = record_id in scoring.index
            in_final = record_id in final.index
            response_row = responses.loc[record_id] if in_responses else None
            scoring_row = scoring.loc[record_id] if in_scoring else None
            final_row = final.loc[record_id] if in_final else None

            if in_responses:
                name = f"{response_row['First name']} {response_row['Last name']}"
            elif in_final:
                name = final_row["Full name"]
            else:
                name = ""
            response_status = response_row["status_canon"] if in_responses else ""
            final_status = final_row["status_canon"] if in_final else ""
            both = in_responses and in_final
            conflict = False
            conflict_type = ""
            conflict_note = ""
            if both:
                if _base_status(response_status) != _base_status(final_status):
                    conflict = True
                    conflict_note = (
                        f"{response_row['status_label']} → "
                        f"{final_row['status_label']}"
                    )
                    if (
                        response_status in {"waitlist", "reuse", "visit"}
                        and final_status in {"approved", "approved_reserved"}
                    ):
                        conflict_type = "progression"
                    elif (
                        response_status in {"approved", "approved_reserved"}
                        and final_status == "waitlist"
                    ):
                        conflict_type = "reversal"
                    else:
                        conflict_type = "other"
                elif response_status != final_status:
                    conflict_note = "different label, same family"
                    conflict_type = "label variation"
            if in_responses and not in_final and not in_scoring:
                only_in = "Responses"
            elif in_scoring and not in_responses and not in_final:
                only_in = "Scoring"
            elif in_final and not in_responses:
                only_in = "final"
            elif in_responses and not in_final:
                only_in = "Responses (no final)"
            else:
                only_in = ""

            person_row = people.loc[record_id] if record_id in people.index else None
            duplicate_of = None
            person_key = ""
            person_ids = ""
            if person_row is not None:
                person_key = str(person_row["person_key"])
                canonical_id = int(person_row["person_canonical_id"])
                person_ids = ", ".join(
                    str(int(value))
                    for value in people[
                        people["person_key"] == person_key
                    ].index
                )
                if canonical_id != record_id:
                    duplicate_of = canonical_id
            rows.append(
                {
                    "ID": record_id,
                    "name": name,
                    "person_key": person_key,
                    "person_ids": person_ids,
                    "duplicate_of": duplicate_of,
                    "in_responses": in_responses,
                    "response_status": response_status,
                    "response_status_label": response_row["status_label"]
                    if in_responses
                    else "",
                    "in_scoring": in_scoring,
                    "call": scoring_row["call_numeric"] if in_scoring else None,
                    "visit": scoring_row["visit_numeric"] if in_scoring else None,
                    "fit": scoring_row["fit_numeric"] if in_scoring else None,
                    "reviewer": scoring_row["reviewer_name"] if in_scoring else "",
                    "in_final": in_final,
                    "final_status": final_status,
                    "final_status_label": final_row["status_label"] if in_final else "",
                    "email_sent": final_row["email_sent"] if in_final else "",
                    "only_in": only_in,
                    "status_conflict": conflict,
                    "status_conflict_type": conflict_type,
                    "conflict_note": conflict_note,
                    "followup_candidates": "; ".join(followup_by_id.get(record_id, [])),
                }
            )
        result = pd.DataFrame(rows)
        result["duplicate_of"] = result["duplicate_of"].astype("Int64")
        return result


class AnalysisBuilder:
    def __init__(self, normalized: NormalizedBundle, linkage: LinkageResult):
        self.normalized = normalized
        self.linkage = linkage

    def status_variants(self) -> pd.DataFrame:
        responses = self.normalized.responses
        rows: list[dict] = []
        total = len(responses)
        for raw, count in responses["Status"].astype(object).value_counts(dropna=False).items():
            missing = bool(pd.isna(raw))
            sample = responses[responses["Status"].astype(object).eq(raw)]
            canonical = sample["status_canon"].iloc[0] if len(sample) else "unknown"
            rows.append(
                {
                    "raw_value": "(blank)" if missing else str(raw),
                    "count": int(count),
                    "pct": round(100 * int(count) / total, 1),
                    "canonical": canonical,
                    "canonical_label": ADOPTION_STATUS_LABELS.get(canonical, canonical),
                    "order": ADOPTION_STATUS_ORDER.index(canonical)
                    if canonical in ADOPTION_STATUS_ORDER
                    else 99,
                }
            )
        result = pd.DataFrame(rows)
        return result.sort_values(
            ["order", "count", "raw_value"], ascending=[True, False, True]
        ).reset_index(drop=True)

    def time_series(self) -> pd.DataFrame:
        responses = self.normalized.responses
        real = responses[~responses["is_test"]].copy()
        real["week_period"] = pd.to_datetime(real["Timestamp"]).dt.to_period("W-SUN")
        real["week_start"] = real["week_period"].dt.start_time
        pivot = (
            real.groupby(["week_start", "status_canon"])
            .size()
            .unstack(fill_value=0)
            .reindex(columns=ADOPTION_STATUS_ORDER, fill_value=0)
            .reset_index()
        )
        pivot["total"] = pivot[ADOPTION_STATUS_ORDER].sum(axis=1)
        pivot["week_label"] = pivot["week_start"].dt.strftime("%d/%m")
        return pivot

    def screening_table(self) -> pd.DataFrame:
        responses = self.normalized.responses
        scoring = self.normalized.scoring
        final = self.normalized.final
        merged = scoring.drop(
            columns=["First name", "Last name"], errors="ignore"
        ).merge(
            responses[
                [
                    "ID",
                    "First name",
                    "Last name",
                    "status_canon",
                    "status_label",
                    "is_test",
                ]
            ].rename(
                columns={
                    "status_canon": "response_status_canon",
                    "status_label": "response_status_label",
                }
            ),
            on="ID",
            how="left",
        ).merge(
            final[["ID", "status_canon", "status_label"]].rename(
                columns={
                    "status_canon": "final_status_canon",
                    "status_label": "final_status_label",
                }
            ),
            on="ID",
            how="left",
        )
        merged["name"] = merged["First name"].fillna("") + " " + merged["Last name"].fillna("")
        merged["name"] = merged["name"].str.strip()
        merged["final_status_label"] = merged["final_status_label"].fillna(
            "Not in final"
        )
        merged["conflict"] = merged.apply(
            lambda row: bool(
                pd.notna(row["final_status_canon"])
                and pd.notna(row["response_status_canon"])
                and _base_status(row["response_status_canon"])
                != _base_status(row["final_status_canon"])
            ),
            axis=1,
        )
        return merged.sort_values("ID").reset_index(drop=True)

    def screening_outcome_summary(self) -> pd.DataFrame:
        screening = self.screening_table().copy()
        screening["final_group"] = screening["final_status_label"].fillna(
            "Not in final"
        )
        grouped = (
            screening.groupby("final_group", sort=False)
            .agg(
                applications=("ID", "count"),
                call_mean=("call_numeric", "mean"),
                visit_mean=("visit_numeric", "mean"),
                fit_mean=("fit_numeric", "mean"),
                score_mean=("score_average", "mean"),
                application_ids=("ID", lambda values: ", ".join(str(int(item)) for item in values)),
            )
            .reset_index()
        )
        for column in ["call_mean", "visit_mean", "fit_mean", "score_mean"]:
            grouped[column] = grouped[column].round(2)
        order = {"Approved": 0, "Waitlist": 1, "Not in final": 2}
        grouped["order"] = grouped["final_group"].map(order).fillna(9)
        return (
            grouped.sort_values(["order", "final_group"])
            .drop(columns="order")
            .reset_index(drop=True)
        )

    def followup_summary(self) -> pd.DataFrame:
        followup = self.normalized.followup.copy()
        followup["status_label"] = pd.Categorical(
            followup["status_label"],
            categories=[
                FOLLOWUP_STATUS_LABELS[item]
                for item in FOLLOWUP_STATUS_ORDER
                if item in FOLLOWUP_STATUS_LABELS
            ],
            ordered=True,
        )
        table = (
            followup.groupby(["status_label", "followup_stage"], observed=False)
            .size()
            .unstack(fill_value=0)
        )
        for column in ["1m", "6m", "none"]:
            if column not in table.columns:
                table[column] = 0
        table = table[["1m", "6m", "none"]]
        table["total"] = table.sum(axis=1)
        table = table[table["total"] > 0].reset_index()
        table["pct_with_followup"] = (
            100 * (table["1m"] + table["6m"]) / table["total"]
        ).round(1)
        return table

    def stage_coverage(self) -> pd.DataFrame:
        responses = self.normalized.responses
        scoring = self.normalized.scoring
        final = self.normalized.final
        real = responses[~responses["is_test"]]
        return pd.DataFrame(
            [
                {
                    "stage": "Rows in Responses",
                    "value": len(responses),
                    "denominator": len(responses),
                    "note": "Includes 2 test rows.",
                },
                {
                    "stage": "Real applications",
                    "value": len(real),
                    "denominator": len(real),
                    "note": "Excludes test rows.",
                },
                {
                    "stage": "With status",
                    "value": int(real["status_canon"].ne("unknown").sum()),
                    "denominator": len(real),
                    "note": "1027 has no status.",
                },
                {
                    "stage": "With scoring",
                    "value": len(scoring),
                    "denominator": len(real),
                    "note": "16 applications scored.",
                },
                {
                    "stage": "In final",
                    "value": len(final),
                    "denominator": len(real),
                    "note": "Includes 1012, absent from Responses.",
                },
                {
                    "stage": "Approved in final",
                    "value": int(final["status_canon"].eq("approved").sum()),
                    "denominator": len(final),
                    "note": "11 approved; 2 waitlisted.",
                },
            ]
        )

    def kpis(self) -> pd.DataFrame:
        responses = self.normalized.responses
        scoring = self.normalized.scoring
        final = self.normalized.final
        followup = self.normalized.followup
        real = responses[~responses["is_test"]]
        links = self.linkage.adopter_links
        evidence = self.linkage.evidence_summary
        reconciliation = self._reconciliation()
        rows = [
            ("response_rows", len(responses), "rows", "All rows, including tests."),
            ("test_rows", int(responses["is_test"].sum()), "rows", "IDs 1000 and 1017."),
            ("real_applications", len(real), "applications", "Excludes test rows."),
            ("unique_people", self.linkage.unique_people, "people", "Person clusters; 1016 and 1023 are the same Mark Shaw."),
            ("duplicate_applications", self.linkage.duplicate_applications, "applications", "Real applications minus unique people."),
            ("with_status", int(real["status_canon"].ne("unknown").sum()), "applications", "1027 has no status."),
            ("with_scoring", len(scoring), "applications", "Scoring sheet."),
            ("in_final", len(final), "applications", "final sheet; includes 1012."),
            ("approved_in_final", int(final["status_canon"].eq("approved").sum()), "applications", "Status Approved."),
            ("waitlist_in_final", int(final["status_canon"].eq("waitlist").sum()), "applications", "Status Waitlist."),
            ("status_conflicts", int(reconciliation["status_conflict"].sum()), "applications", "Responses vs final, raw differences."),
            ("status_progressions", int(reconciliation["status_conflict_type"].eq("progression").sum()), "applications", "Waitlist/Reuse/Visit → Approved."),
            ("status_reversals", int(reconciliation["status_conflict_type"].eq("reversal").sum()), "applications", "Approved → Waitlist."),
            ("followup_rows", len(followup), "rows", "Follow-up list."),
            ("followup_adopters", followup["adopter"].nunique(), "adopters", "Abbreviated name."),
            ("followup_animals", followup["animal_code"].nunique(), "codes", "DOG-0424 is a fallback reservation, not a duplicate."),
            ("followup_episodes", len(followup) - int(followup["status_canon"].eq("swapped").sum()), "episodes", "Rows minus the intermediate swap row."),
            ("followup_without_record", int(followup["followup_stage"].eq("none").sum()), "rows", "No 1m/6m."),
            ("returns", int(followup["status_canon"].isin(["returned", "returned_trial"]).sum()), "rows", "Returned + Returned (trial)."),
            ("phone_exact", int(evidence["phone_exact"].sum()), "adopters", "Exact phone after normalisation."),
            ("name_candidates", int(evidence["name_match"].sum()), "adopters", "Name + initial."),
            ("linkage_resolved", int(links["ambiguity"].eq("resolved").sum()), "adopters", "Deterministic exact phone, status, duplicate or household-pet rule."),
            ("no_candidate", int((links["candidate_count"] == 0).sum()), "adopters", "No name/phone candidate."),
            ("ambiguous", int(links["ambiguity"].eq("ambiguous").sum()), "adopters", "More than one identity candidate; no deterministic tie-break."),
            ("dob_mismatch", int(self.normalized.dob_audit["mismatch"].sum()), "records", "dob_clean differs from dd/mm/yyyy parsing."),
            ("dob_validated_by_duplicate", 1, "records", "1016's dob_clean is confirmed by 1023's ISO date."),
        ]
        return pd.DataFrame(rows, columns=["metric", "value", "unit", "definition"])

    def _reconciliation(self) -> pd.DataFrame:
        return StatusReconciler(self.normalized, self.linkage).reconciliation()

    def summary_reconciliation(self) -> pd.DataFrame:
        responses = self.normalized.responses
        real = responses[~responses["is_test"]]
        formula_values = {
            "Total requests": 26,
            "Approved": 9,
            "Waitlist": 5,
            "List B": 1,
            "Rejected": 3,
            "Reuse": 1,
            "Home visit": 1,
            "Reserved": 2,
            "Sum": 20,
        }
        canonical_values = {
            "Total requests": len(real),
            "Approved": int(real["status_canon"].isin(["approved", "approved_reserved"]).sum()),
            "Waitlist": int(real["status_canon"].eq("waitlist").sum()),
            "List B": int(real["status_canon"].eq("list_b").sum()),
            "Rejected": int(real["status_canon"].eq("rejected").sum()),
            "Reuse": int(real["status_canon"].eq("reuse").sum()),
            "Home visit": int(self.normalized.scoring["visit_numeric"].notna().sum()),
            "Reserved": int(real["status_canon"].eq("approved_reserved").sum()),
            "Sum": len(real),
        }
        notes = {
            "Total requests": "COUNTA counts 26 IDs, including 2 test rows; real = 24 applications (23 unique people; 1016/1023 are the same person).",
            "Approved": "Approved* counts 7 Approved + 2 reserved; misses 'Aproved'. Canonical = 10 applications.",
            "Waitlist": "Matches after case/whitespace normalisation.",
            "List B": "Formula only catches exact 'List B'; there are 3 variants.",
            "Rejected": "Matches; includes 'Rejected - previous return'.",
            "Reuse": "Matches.",
            "Home visit": "Formula counts the 'visit' status; there are 16 visits with a score.",
            "Reserved": "Matches 'Approved - reserved'.",
            "Sum": "Formula sums to 20; the real total has 24 applications (23 people), including 3 with no status.",
        }
        rows = []
        for metric in formula_values:
            rows.append(
                {
                    "metric": metric,
                    "summary_formula": formula_values[metric],
                    "recomputed": canonical_values[metric],
                    "difference": canonical_values[metric] - formula_values[metric],
                    "note": notes[metric],
                }
            )
        return pd.DataFrame(rows)


class IssueRegister:
    def __init__(
        self,
        normalized: NormalizedBundle,
        linkage: LinkageResult,
        analysis: AnalysisBuilder,
    ):
        self.normalized = normalized
        self.linkage = linkage
        self.analysis = analysis

    def build(self) -> pd.DataFrame:
        responses = self.normalized.responses
        scoring = self.normalized.scoring
        final = self.normalized.final
        followup = self.normalized.followup
        reconciliation = self.analysis._reconciliation()
        links = self.linkage.adopter_links
        evidence = self.linkage.evidence_summary
        dob_mismatch = int(self.normalized.dob_audit["mismatch"].sum())
        status_variants = responses["Status"].nunique(dropna=False)
        phone_formats = responses["phone_format"].nunique()
        identity_types = responses["identity_type"].nunique()
        conflicts = int(reconciliation["status_conflict"].sum())
        issues = [
            SemanticIssue(
                "I01",
                "Structure",
                "Two-row header and helper columns",
                "Responses has groups in row 1 and field names in row 2; dob_clean is a helper.",
                1,
                "1 sheet",
                "Sheet copied and adapted across campaigns.",
                2,
                "High",
                "Dedicated loader; preserve the original file.",
            ),
            SemanticIssue(
                "I02",
                "Structure",
                "Test rows in the production base",
                "IDs 1000 and 1017 are named 'Test'/'test'.",
                int(responses["is_test"].sum()),
                "26 rows",
                "The team tests the form in the live sheet.",
                3,
                "High",
                "is_test flag; exclude from KPIs without deleting.",
            ),
            SemanticIssue(
                "I03",
                "Identity",
                "Missing, duplicate or downstream-only IDs",
                "1006 does not exist; 1012 exists only in final; 1016 and 1023 are the same person.",
                3,
                "27 IDs in the universe",
                "Rows deleted/inserted between campaigns, parallel lists and re-submitted requests.",
                4,
                "High",
                "Immutable person/application IDs and an event log by source.",
            ),
            SemanticIssue(
                "I04",
                "Status",
                "Status differences between Adoptions and final",
                f"{conflicts} of 12 overlapping IDs differ; "
                f"{int(reconciliation['status_conflict_type'].eq('progression').sum())} are progressions "
                f"and {int(reconciliation['status_conflict_type'].eq('reversal').sum())} are reversals.",
                conflicts,
                "12 overlapping IDs",
                "Follow-up updates after calls; Adoptions does not revise, and later decisions are appended.",
                5,
                "High",
                "Status per team + timestamp, not a single mutable field.",
            ),
            SemanticIssue(
                "I05",
                "Status",
                "Many variants for few statuses",
                f"{status_variants} Status categories, including blank, for 8 canonical statuses.",
                len(responses),
                "26 rows",
                "Fast entry during the campaign, with no closed list.",
                3,
                "High",
                "Crosswalk + form validation.",
            ),
            SemanticIssue(
                "I06",
                "Formula",
                "Formulas without cached values",
                "60 in Scoring, 13 in Summary and 10 in Sheet3.",
                83,
                "83 formula cells",
                "File distributed and read outside Excel; not recalculated.",
                3,
                "High",
                "Do not read KPIs from formulas; recompute in the pipeline.",
            ),
            SemanticIssue(
                "I07",
                "Formula",
                "Cells with errors",
                "4 #REF! in Scoring and 1 #ERROR! in Responses.",
                5,
                "5 cells",
                "Row insertion/removal and copy/paste across campaigns.",
                4,
                "High",
                "Fixed IDs, validation and key-based formulas, not positional ones.",
            ),
            SemanticIssue(
                "I08",
                "Identity",
                "Date parsing differs from dd/mm/yyyy",
                f"{dob_mismatch} records with dob_clean different from dd/mm/yyyy; "
                "1016 is confirmed by 1023, so the raw entry is mm/dd.",
                dob_mismatch,
                "26 records",
                "The form asks for dd/mm/yyyy, but entries and Excel locale mix dd/mm and mm/dd.",
                4,
                "High",
                "Explicit parsing with dayfirst=True, plus a cross-record audit before using DOB as a key.",
            ),
            SemanticIssue(
                "I09",
                "Identity",
                "Phones in mixed formats",
                f"{phone_formats} formats, 2 placeholders and 1 error.",
                int(responses["Phone"].notna().sum()),
                "24 filled phone numbers",
                "Free-text field and copy/paste between rows.",
                4,
                "High",
                "Normalise to E.164 and separate mobile/landline.",
            ),
            SemanticIssue(
                "I10",
                "Identity",
                "Identity field mixes types",
                f"{identity_types} types: adopter number, document, number, placeholder, missing.",
                len(responses),
                "26 records",
                "The form accepts adopter number or document in the same field.",
                4,
                "High",
                "Separate type and value; use adopter_id when available.",
            ),
            SemanticIssue(
                "I11",
                "Process",
                "Cross-team linkage almost absent by phone",
                f"{int(evidence['phone_exact'].sum())} of {len(evidence)} Follow-up adopters have an exact phone in Adoptions; "
                f"deterministic name/status rules resolve {int(links['ambiguity'].eq('resolved').sum())}, "
                f"leaving {int(links['ambiguity'].eq('ambiguous').sum())} ambiguous.",
                int(evidence["phone_exact"].sum()),
                f"{len(evidence)} adopters",
                "Different, shared or hastily entered phones; Follow-up records only an abbreviated name.",
                5,
                "High",
                "Add an application/person ID to the Follow-up export; keep a human-review seam for the residual.",
            ),
            SemanticIssue(
                "I12",
                "Process",
                "Incomplete follow-up",
                f"{int(followup['followup_stage'].eq('none').sum())} of {len(followup)} rows lack 1m/6m.",
                int(followup["followup_stage"].eq("none").sum()),
                f"{len(followup)} rows",
                "Current list, updated after contact; not all placements have follow-up.",
                4,
                "High",
                "Status and date fields per contact; distinguish not applicable from unknown.",
            ),
            SemanticIssue(
                "I13",
                "Time",
                "Follow-up dates lack a year",
                "16 of 16 updated values are month-day (Jul–Dec).",
                len(followup),
                "16 rows",
                "Informal weekly list, not ISO 8601.",
                4,
                "High",
                "Store a full timestamp with year and timezone.",
            ),
            SemanticIssue(
                "I14",
                "Process",
                "Animal reuse and animal swap",
                "DOG-0424 is the same Lola offered to Danielle H. (not collected) and then Harry A. (waitlist); DOG-0418 becomes DOG-0421.",
                3,
                "16 rows",
                "Fallback reservation and animal swap during the trial; not duplicate placements.",
                3,
                "High",
                "placement_id + status history, not just animal_code.",
            ),
            SemanticIssue(
                "I15",
                "Structure",
                "Ref missing in most records",
                f"{int(responses['Ref'].isna().sum())} of 26 lack Ref.",
                int(responses["Ref"].isna().sum()),
                "26 rows",
                "Reviewers' internal convention; not a universal key.",
                2,
                "Medium",
                "Preserve, document and do not use as a linkage key.",
            ),
            SemanticIssue(
                "I16",
                "Status",
                "Summary confuses visit with outcome",
                "The 'Home visit' formula counts the 'visit' status; there are 16 visits with a score.",
                1,
                "1 KPI",
                "Old formula inherited from previous campaigns.",
                3,
                "High",
                "Separate scheduled visit, completed visit and outcome.",
            ),
            SemanticIssue(
                "I17",
                "Process",
                "final includes a record absent from Responses",
                "1012 Sophie Webb exists only in final.",
                1,
                "13 rows in final",
                "Record created directly in the final list.",
                4,
                "High",
                "Event model with source and timestamp; reconcile by name.",
            ),
            SemanticIssue(
                "I18",
                "Process",
                "Follow-up adopters without a candidate",
                f"{int((links['candidate_count'] == 0).sum())} adopters have no candidate in Adoptions.",
                int((links["candidate_count"] == 0).sum()),
                f"{len(links)} adopters",
                "They may be from another cohort, another centre, or have different names.",
                3,
                "Medium",
                "Confirm the list's scope before assuming records are missing.",
            ),
            SemanticIssue(
                "I19",
                "Identity",
                "Same person appears in two application rows",
                "1016 and 1023 Mark Shaw share adopter no. 060064440, phone 07570 468615 and DOB 1985-10-02.",
                2,
                "24 real applications",
                "The form invites a second submission to correct a request; a re-application creates a new row.",
                4,
                "High",
                "person_id + application_id; allow several applications per person and resolve to one person.",
            ),
        ]
        result = pd.DataFrame([issue.__dict__ for issue in issues])
        result["priority_score"] = [issue.priority_score for issue in issues]
        return result.sort_values(
            ["priority_score", "impact", "frequency"], ascending=False
        ).reset_index(drop=True)
