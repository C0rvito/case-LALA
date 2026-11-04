from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from .normalize import _as_text


@dataclass
class LinkageResult:
    adopter_links: pd.DataFrame
    candidate_pairs: pd.DataFrame
    animal_identity: pd.DataFrame
    animal_matches: pd.DataFrame
    evidence_summary: pd.DataFrame
    person_map: pd.DataFrame
    unique_people: int
    duplicate_applications: int


class AdopterLinker:
    def __init__(
        self,
        responses: pd.DataFrame,
        followup: pd.DataFrame,
        final: pd.DataFrame | None = None,
    ):
        self.responses = responses[~responses["is_test"]].copy()
        self.followup = followup.copy()
        self.final = final.copy() if final is not None else pd.DataFrame()
        self._specific_names = {
            "thor",
            "coco",
            "lola",
            "luna",
            "kira",
        }
        self._prepare_people()

    def _prepare_people(self) -> None:
        final_ids: set[int] = set()
        final_status: dict[int, str] = {}
        if not self.final.empty:
            final_ids = {int(value) for value in self.final["ID"].dropna()}
            final_status = {
                int(row["ID"]): str(row.get("status_canon", ""))
                for _, row in self.final.iterrows()
            }
        self.responses["in_final"] = (
            self.responses["ID"].astype(int).isin(final_ids)
        )
        self.responses["final_status_canon"] = (
            self.responses["ID"].astype(int).map(final_status).fillna("")
        )

        def person_key(row: pd.Series) -> str:
            identifier = _as_text(row["Adopter no. or passport/licence"]).upper()
            if identifier and identifier not in {"ID", "NAN", "NONE"}:
                return f"id:{identifier}"
            if (
                row["name_norm"]
                and pd.notna(row["phone_norm"])
                and not row["phone_is_placeholder"]
                and pd.notna(row["dob_parsed"])
            ):
                return (
                    f"name:{row['name_norm']}|phone:{row['phone_norm']}"
                    f"|dob:{row['dob_parsed'].date()}"
                )
            if (
                row["name_norm"]
                and pd.notna(row["phone_norm"])
                and not row["phone_is_placeholder"]
            ):
                return f"name:{row['name_norm']}|phone:{row['phone_norm']}"
            return f"row:{int(row['ID'])}"

        self.responses["person_key"] = self.responses.apply(person_key, axis=1)
        canonical: dict[str, int] = {}
        for key, group in self.responses.groupby("person_key", sort=False):
            in_final = group[group["in_final"]]
            canonical[key] = int(
                (in_final if not in_final.empty else group)["ID"].min()
            )
        self.responses["person_canonical_id"] = self.responses["person_key"].map(
            canonical
        )
        self._person_ids = {
            key: sorted(int(value) for value in group["ID"])
            for key, group in self.responses.groupby("person_key", sort=False)
        }

    def _followup_adopters(self) -> pd.DataFrame:
        rows: list[dict] = []
        for adopter, group in self.followup.groupby("adopter", sort=False):
            phones = group["phone_norm"].dropna().unique().tolist()
            rows.append(
                {
                    "adopter": adopter,
                    "adopter_key": _as_text(adopter).casefold(),
                    "adopter_first": group["adopter_first"].iloc[0],
                    "adopter_last_initial": group["adopter_last_initial"].iloc[0],
                    "phone_norm": phones[0] if len(phones) == 1 else None,
                    "animal_names": ", ".join(sorted(set(group["animal_name"].astype(str)))),
                    "animal_codes": ", ".join(sorted(set(group["animal_code"].astype(str)))),
                    "statuses": ", ".join(sorted(set(group["status_label"].astype(str)))),
                    "rows": len(group),
                }
            )
        return pd.DataFrame(rows)

    def _candidate_pairs(self, adopters: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict] = []
        for _, follower in adopters.iterrows():
            follower_animals = [
                _as_text(item).casefold()
                for item in str(follower["animal_names"]).split(",")
            ]
            for _, applicant in self.responses.iterrows():
                evidence: list[str] = []
                phone_match = bool(
                    follower["phone_norm"]
                    and applicant["phone_norm"] == follower["phone_norm"]
                    and not applicant["phone_is_placeholder"]
                )
                name_match = (
                    follower["adopter_first"] == applicant["first_name_norm"]
                    and follower["adopter_last_initial"] == applicant["last_initial"]
                )
                first_name_match = (
                    follower["adopter_first"] == applicant["first_name_norm"]
                )
                animal_match = any(
                    animal
                    and animal in self._specific_names
                    and animal in _as_text(applicant["Animal"]).casefold()
                    for animal in follower_animals
                )
                if phone_match:
                    evidence.append("exact phone")
                if name_match:
                    evidence.append("name + initial")
                elif first_name_match:
                    evidence.append("first name")
                if animal_match:
                    evidence.append("specific animal")
                if not evidence:
                    continue
                score = 0
                if phone_match:
                    score += 55
                if name_match:
                    score += 40
                elif first_name_match:
                    score += 25
                if animal_match:
                    score += 10
                if score >= 70:
                    confidence = "strong"
                elif score >= 45:
                    confidence = "medium"
                else:
                    confidence = "weak"
                candidate_status = str(applicant["status_canon"])
                candidate_final_status = str(applicant["final_status_canon"])
                candidate_positive = candidate_status in {
                    "approved",
                    "approved_reserved",
                } or candidate_final_status == "approved"
                rows.append(
                    {
                        "adopter_b": follower["adopter"],
                        "adopter_key": follower["adopter_key"],
                        "candidate_id": int(applicant["ID"]),
                        "candidate_name": f"{applicant['First name']} {applicant['Last name']}",
                        "candidate_status": applicant["status_label"],
                        "candidate_status_canon": candidate_status,
                        "candidate_final_status": candidate_final_status,
                        "candidate_in_final": bool(applicant["in_final"]),
                        "candidate_positive": candidate_positive,
                        "candidate_person_key": applicant["person_key"],
                        "candidate_canonical_id": int(
                            applicant["person_canonical_id"]
                        ),
                        "candidate_person_ids": ", ".join(
                            str(value)
                            for value in self._person_ids[applicant["person_key"]]
                        ),
                        "candidate_phone": applicant["phone_norm"],
                        "candidate_animal": _as_text(applicant["Animal"]),
                        "candidate_household_animals": applicant["other_animal_type"],
                        "score": score,
                        "confidence": confidence,
                        "evidence": " + ".join(evidence),
                        "phone_match": phone_match,
                        "name_match": name_match,
                        "animal_match": animal_match,
                    }
                )
        if not rows:
            return pd.DataFrame(
                columns=[
                    "adopter_b",
                    "adopter_key",
                    "candidate_id",
                    "candidate_name",
                    "candidate_status",
                    "candidate_status_canon",
                    "candidate_final_status",
                    "candidate_in_final",
                    "candidate_positive",
                    "candidate_person_key",
                    "candidate_canonical_id",
                    "candidate_person_ids",
                    "candidate_phone",
                    "candidate_animal",
                    "candidate_household_animals",
                    "score",
                    "confidence",
                    "evidence",
                    "phone_match",
                    "name_match",
                    "animal_match",
                    "rank",
                ]
            )
        pairs = pd.DataFrame(rows)
        pairs["rank"] = pairs.groupby("adopter_key")["score"].rank(
            method="first", ascending=False
        )
        return pairs.sort_values(
            ["adopter_key", "score", "candidate_id"],
            ascending=[True, False, True],
        ).reset_index(drop=True)

    @staticmethod
    def _collapse_people(group: pd.DataFrame) -> pd.DataFrame:
        if group.empty:
            return group
        ordered = group.sort_values(
            [
                "phone_match",
                "candidate_in_final",
                "candidate_positive",
                "score",
                "candidate_id",
            ],
            ascending=[False, False, False, False, True],
        )
        rows: list[dict] = []
        for _, person in ordered.groupby("candidate_person_key", sort=False):
            top = person.iloc[0].to_dict()
            top["person_candidate_ids"] = ", ".join(
                str(int(value)) for value in sorted(person["candidate_id"].unique())
            )
            rows.append(top)
        return pd.DataFrame(rows)

    def _followup_species(self, follower: pd.Series) -> set[str]:
        names = {
            _as_text(value).casefold()
            for value in str(follower["animal_names"]).split(",")
            if _as_text(value)
        }
        rows = self.followup[
            self.followup["animal_name"].astype(str).str.casefold().isin(names)
        ]
        return {
            _as_text(value).casefold()
            for value in rows["species"].dropna().unique()
            if _as_text(value)
        }

    @staticmethod
    def _species_match(candidate: pd.Series, species: set[str]) -> bool:
        if not species:
            return False
        household = _as_text(candidate["candidate_household_animals"]).casefold()
        if not household or household in {"unknown", "none", "unspecified", "animal unspecified"}:
            return False
        return all(item in household for item in species)

    @staticmethod
    def _alternative_label(row: pd.Series) -> str:
        status = _as_text(row["candidate_status"])
        if _as_text(row["candidate_final_status"]):
            status += f" / final {row['candidate_final_status']}"
        return (
            f"{int(row['candidate_id'])} {row['candidate_name']} "
            f"({int(row['score'])}, {status})"
        )

    def _adopter_summary(
        self, adopters: pd.DataFrame, pairs: pd.DataFrame
    ) -> pd.DataFrame:
        rows: list[dict] = []
        for _, follower in adopters.iterrows():
            group = pairs[pairs["adopter_key"] == follower["adopter_key"]]
            identity = group[group["phone_match"] | group["name_match"]]
            if identity.empty:
                rows.append(
                    {
                        **follower.to_dict(),
                        "best_id": None,
                        "best_name": "",
                        "best_status": "",
                        "best_final_status": "",
                        "best_score": 0,
                        "confidence": "no match",
                        "ambiguity": "no candidate",
                        "resolution": "no candidate",
                        "resolution_rule": "No name, phone or animal candidate in Adoptions.",
                        "same_person_ids": "",
                        "evidence": "",
                        "alternatives": "",
                        "candidate_count": 0,
                    }
                )
                continue

            all_pool = self._collapse_people(identity)
            pool = all_pool
            phone_pool = pool[pool["phone_match"]]
            if not phone_pool.empty:
                top = phone_pool.iloc[0]
                confidence = "strong"
                ambiguity = "resolved"
                resolution = "exact phone"
                rule = "Exact normalised phone; name confirms the same person."
            else:
                positive = pool[pool["candidate_positive"]]
                if positive.empty:
                    if len(pool) == 1:
                        top = pool.iloc[0]
                        confidence = "weak"
                        ambiguity = "resolved"
                        resolution = "unique name"
                        rule = "Only one name + initial candidate; no approved/final record to confirm it."
                    else:
                        top = None
                        confidence = "ambiguous"
                        ambiguity = "ambiguous"
                        resolution = "ambiguous"
                        rule = (
                            "More than one name + initial candidate; none is approved "
                            "or in final. Do not merge without human review."
                        )
                else:
                    pool = positive
                    if len(pool) == 1:
                        top = pool.iloc[0]
                        confidence = "medium"
                        ambiguity = "resolved"
                        resolution = "positive candidate"
                        if len(top.get("person_candidate_ids", "").split(",")) > 1:
                            resolution = "person duplicate"
                            rule = (
                                "Person cluster "
                                f"{top['person_candidate_ids']} (adopter no., phone "
                                "and DOB); the application in final is approved."
                            )
                        else:
                            rule = (
                                "Single approved/in-final name candidate after "
                                "excluding rejected/List B alternatives."
                            )
                    else:
                        species = self._followup_species(follower)
                        matches = pool[
                            pool.apply(
                                lambda row: self._species_match(row, species),
                                axis=1,
                            )
                        ]
                        if len(matches) == 1:
                            top = matches.iloc[0]
                            confidence = "medium"
                            ambiguity = "resolved"
                            resolution = "household pets"
                            rule = (
                                "Two approved candidates; the Follow-up animal species "
                                "matches exactly one household's existing pets."
                            )
                        else:
                            top = None
                            confidence = "ambiguous"
                            ambiguity = "ambiguous"
                            resolution = "ambiguous"
                            rule = (
                                "Two approved candidates and no deterministic tie-break. "
                                "Do not merge without human review."
                            )

            alternatives = all_pool.copy()
            if top is not None:
                alternatives = alternatives[
                    alternatives["candidate_id"] != top["candidate_id"]
                ]
            alternatives = alternatives[alternatives["score"] >= 25].head(3)
            if top is None:
                best_id = None
                best_name = ""
                best_status = ""
                best_final_status = ""
                best_score = 0
                evidence = ""
                same_person_ids = ""
            else:
                best_id = int(top["candidate_id"])
                best_name = top["candidate_name"]
                best_status = top["candidate_status"]
                best_final_status = top["candidate_final_status"]
                best_score = int(top["score"])
                evidence = top["evidence"]
                same_person_ids = (
                    top["person_candidate_ids"]
                    if len(str(top["person_candidate_ids"]).split(",")) > 1
                    else ""
                )
            rows.append(
                {
                    **follower.to_dict(),
                    "best_id": best_id,
                    "best_name": best_name,
                    "best_status": best_status,
                    "best_final_status": best_final_status,
                    "best_score": best_score,
                    "confidence": confidence,
                    "ambiguity": ambiguity,
                    "resolution": resolution,
                    "resolution_rule": rule,
                    "same_person_ids": same_person_ids,
                    "evidence": evidence,
                    "alternatives": "; ".join(
                        self._alternative_label(row)
                        for _, row in alternatives.iterrows()
                    ),
                    "candidate_count": int(len(all_pool)),
                }
            )
        result = pd.DataFrame(rows)
        result["best_id"] = result["best_id"].astype("Int64")
        return result

    def _evidence_summary(
        self, adopters: pd.DataFrame, pairs: pd.DataFrame
    ) -> pd.DataFrame:
        rows: list[dict] = []
        for _, follower in adopters.iterrows():
            group = pairs[pairs["adopter_key"] == follower["adopter_key"]]
            rows.append(
                {
                    "adopter": follower["adopter"],
                    "phone_exact": bool(group["phone_match"].any()),
                    "name_match": bool(group["name_match"].any()),
                    "animal_match": bool(group["animal_match"].any()),
                    "candidate_count": int(len(group)),
                }
            )
        return pd.DataFrame(rows)

    def build(self) -> LinkageResult:
        adopters = self._followup_adopters()
        pairs = self._candidate_pairs(adopters)
        links = self._adopter_summary(adopters, pairs)
        evidence = self._evidence_summary(adopters, pairs)
        animal_linker = AnimalLinker(self.responses, self.followup)
        unique_people = int(self.responses["person_key"].nunique())
        return LinkageResult(
            adopter_links=links,
            candidate_pairs=pairs,
            animal_identity=animal_linker.identity(),
            animal_matches=animal_linker.matches(),
            evidence_summary=evidence,
            person_map=self.responses[
                [
                    "ID",
                    "person_key",
                    "person_canonical_id",
                    "in_final",
                    "final_status_canon",
                ]
            ].copy(),
            unique_people=unique_people,
            duplicate_applications=int(len(self.responses) - unique_people),
        )


class AnimalLinker:
    def __init__(self, responses: pd.DataFrame, followup: pd.DataFrame):
        self.responses = responses[~responses["is_test"]].copy()
        self.followup = followup.copy()
        self.specific_names = {"thor", "coco", "lola", "luna", "kira"}

    def identity(self) -> pd.DataFrame:
        rows: list[dict] = []
        for code, group in self.followup.groupby("animal_code", sort=True):
            notes = " ".join(group["notes"].fillna("").astype(str))
            target = re.search(r"moves to\s+(DOG-\d+)", notes, re.IGNORECASE)
            source = re.search(r"from\s+(DOG-\d+)", notes, re.IGNORECASE)
            rows.append(
                {
                    "animal_code": code,
                    "species": group["species"].iloc[0],
                    "animal_name": group["animal_name"].iloc[0],
                    "adopters": "; ".join(group["adopter"].astype(str)),
                    "statuses": "; ".join(group["status_label"].astype(str)),
                    "rows": len(group),
                    "duplicate_code": len(group) > 1,
                    "swap_target": target.group(1) if target else "",
                    "swap_source": source.group(1) if source else "",
                    "notes": notes.strip(),
                }
            )
        return pd.DataFrame(rows)

    def matches(self) -> pd.DataFrame:
        rows: list[dict] = []
        for _, animal in self.followup.iterrows():
            name = _as_text(animal["animal_name"]).casefold()
            if name not in self.specific_names:
                continue
            hits = self.responses[
                self.responses["Animal"]
                .fillna("")
                .astype(str)
                .str.casefold()
                .str.contains(re.escape(name), regex=True)
            ]
            for _, applicant in hits.iterrows():
                rows.append(
                    {
                        "animal_code": animal["animal_code"],
                        "animal_name": animal["animal_name"],
                        "adopter_b": animal["adopter"],
                        "candidate_id": int(applicant["ID"]),
                        "candidate_name": f"{applicant['First name']} {applicant['Last name']}",
                        "candidate_status": applicant["status_label"],
                        "candidate_animal": applicant["Animal"],
                    }
                )
        return pd.DataFrame(rows)
