from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from .config import (
    ADOPTION_STATUS_GROUPS,
    ADOPTION_STATUS_LABELS,
    CAMPAIGN_END,
    FOLLOWUP_STATUS_LABELS,
    REVIEWER_NAMES,
)
from .io import DataBundle


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _as_text(value: Any) -> str:
    return "" if _is_missing(value) else str(value).strip()


class NameNormalizer:
    @staticmethod
    def clean(value: Any) -> str:
        text = _as_text(value)
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def key(cls, value: Any) -> str:
        return cls.clean(value).casefold()

    @classmethod
    def first(cls, value: Any) -> str:
        parts = cls.clean(value).split()
        return parts[0].casefold() if parts else ""

    @classmethod
    def last_initial(cls, value: Any) -> str:
        parts = cls.clean(value).split()
        return parts[-1][0].casefold() if parts else ""


class PhoneNormalizer:
    PLACEHOLDERS = {
        "07900000000",
        "07500000000",
        "07000000000",
        "01234567890",
    }

    @staticmethod
    def _digits(value: Any) -> str:
        return re.sub(r"\D", "", _as_text(value))

    @classmethod
    def normalize(cls, value: Any) -> tuple[str | None, str]:
        text = _as_text(value)
        if not text:
            return None, "missing"
        if text.startswith("#"):
            return None, "error"
        digits = cls._digits(text)
        if not digits:
            return None, "error"
        if digits.startswith("0044"):
            digits = digits[4:]
        if digits.startswith("44") and len(digits) >= 11:
            digits = "0" + digits[2:]
        if len(digits) == 10 and not digits.startswith("0"):
            digits = "0" + digits
        if len(digits) < 10 or len(digits) > 11:
            return None, "other"
        if digits in cls.PLACEHOLDERS:
            return digits, "placeholder"
        if digits.startswith("07"):
            return digits, "mobile 07"
        if digits.startswith(("01", "02", "03")):
            return digits, "landline 01/02/03"
        return digits, "other"

    @classmethod
    def is_placeholder(cls, normalized: str | None) -> bool:
        return normalized in cls.PLACEHOLDERS


class DateNormalizer:
    ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T].*)?$")
    SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$")
    DASH_RE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{2,4})$")
    TEXT_RE = re.compile(r"[A-Za-zÀ-ÿ]")

    @classmethod
    def parse(cls, value: Any) -> tuple[pd.Timestamp | pd.NaT, str, bool]:
        if _is_missing(value):
            return pd.NaT, "missing", False
        if isinstance(value, pd.Timestamp):
            return value.normalize(), "timestamp", False
        if isinstance(value, (datetime, date)):
            return pd.Timestamp(value).normalize(), "timestamp", False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if 20000 <= float(value) <= 60000:
                parsed = pd.Timestamp("1899-12-30") + pd.to_timedelta(
                    int(value), unit="D"
                )
                return parsed.normalize(), "Excel serial", False
        text = _as_text(value)
        if not text:
            return pd.NaT, "missing", False
        if cls.ISO_RE.match(text):
            parsed = pd.to_datetime(text, errors="coerce")
            return (
                (parsed.normalize() if not pd.isna(parsed) else pd.NaT),
                "ISO (YYYY-MM-DD)",
                False,
            )
        match = cls.SLASH_RE.match(text)
        if match:
            first, second = int(match.group(1)), int(match.group(2))
            ambiguous = first <= 12 and second <= 12
            parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
            fmt = "dd/mm/yyyy" if len(match.group(3)) == 4 else "dd/mm/yy"
            return (
                (parsed.normalize() if not pd.isna(parsed) else pd.NaT),
                fmt,
                ambiguous,
            )
        match = cls.DASH_RE.match(text)
        if match:
            first, second = int(match.group(1)), int(match.group(2))
            ambiguous = first <= 12 and second <= 12
            parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
            fmt = "d-m-yyyy" if len(match.group(3)) == 4 else "d-m-yy"
            return (
                (parsed.normalize() if not pd.isna(parsed) else pd.NaT),
                fmt,
                ambiguous,
            )
        if cls.TEXT_RE.search(text):
            parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
            return (
                (parsed.normalize() if not pd.isna(parsed) else pd.NaT),
                "text (month name)",
                False,
            )
        parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
        return (
            (parsed.normalize() if not pd.isna(parsed) else pd.NaT),
            "other",
            False,
        )

    @staticmethod
    def age_at(dob: pd.Timestamp | pd.NaT, reference: str = CAMPAIGN_END) -> float | None:
        if pd.isna(dob):
            return None
        reference_date = pd.Timestamp(reference)
        return (reference_date - dob).days / 365.25


class IdentityNormalizer:
    ADOPTER_RE = re.compile(r"^HW\d{2}-\d+$", re.IGNORECASE)
    DOCUMENT_RE = re.compile(r"^[A-Z]{2,}\d+[A-Z0-9]*$", re.IGNORECASE)

    @classmethod
    def classify(cls, value: Any) -> str:
        text = _as_text(value)
        if not text:
            return "missing"
        if text.upper() == "ID":
            return "placeholder"
        if cls.ADOPTER_RE.match(text):
            return "adopter number (HW)"
        if cls.DOCUMENT_RE.match(text):
            return "alphanumeric document"
        if text.isdigit():
            return "number"
        return "other"


class CategoryNormalizer:
    @staticmethod
    def town(value: Any) -> str:
        text = _as_text(value).casefold()
        if not text:
            return "Unknown"
        if "bristol" in text or text in {"bris", "bedminster", "bs3"}:
            return "Bristol"
        if "bath" in text or "banes" in text:
            return "Bath & NE Somerset"
        if any(
            token in text
            for token in (
                "n somerset",
                "north somerset",
                "weston",
                "wsm",
                "portishead",
                "clevedon",
                "nailsea",
            )
        ):
            return "North Somerset"
        if any(
            token in text
            for token in ("s glos", "south glos", "yate", "kingswood", "keynsham")
        ):
            return "South Gloucestershire"
        if "frome" in text or "somerset" in text:
            return "Somerset (other)"
        return "Other"

    @staticmethod
    def home_type(value: Any) -> str:
        text = _as_text(value).casefold()
        if not text:
            return "Unknown"
        if "flat" in text:
            return "Flat"
        if "parents" in text:
            return "Parents' home"
        if "shared" in text:
            return "Shared house"
        if "house" in text:
            return "House"
        return "Other"

    @staticmethod
    def tenure(value: Any) -> str:
        text = _as_text(value).casefold()
        if not text:
            return "Unknown"
        if "rent" in text:
            return "Rented"
        if "own" in text:
            return "Owned"
        if "parents" in text:
            return "Family"
        if "shared" in text:
            return "Shared"
        return "Other"

    @staticmethod
    def other_animals(value: Any) -> tuple[float | None, str, str]:
        text = _as_text(value)
        lower = text.casefold()
        if not lower:
            return None, "unknown", ""
        if lower in {"no", "none"}:
            return 0, "none", ""
        words = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
        }
        count: float | None = None
        for word, number in words.items():
            if re.search(rf"\b{word}\b", lower):
                count = float(number)
                break
        if count is None:
            number_match = re.search(r"\b(\d+)\b", lower)
            count = float(number_match.group(1)) if number_match else 1.0
        has_cat = "cat" in lower
        has_dog = "dog" in lower
        if has_cat and has_dog:
            kind = "cat and dog"
        elif has_cat:
            kind = "cat"
        elif has_dog:
            kind = "dog"
        elif lower.startswith("yes"):
            kind = "animal unspecified"
        else:
            kind = "unspecified"
        return count, kind, text

    @staticmethod
    def source(value: Any) -> str:
        text = _as_text(value).casefold()
        if not text:
            return "Unknown"
        if "instagram" in text or "insta" in text or text == "ig":
            return "Instagram"
        if "website" in text:
            return "Website"
        if "facebook" in text:
            return "Facebook"
        if "tiktok" in text:
            return "TikTok"
        if "volunteer" in text:
            return "Volunteer"
        if "word of mouth" in text or "friend" in text:
            return "Word of mouth"
        return "Other"

    @staticmethod
    def animal_interest(value: Any) -> str:
        text = _as_text(value).casefold()
        if not text:
            return "Unknown"
        if "whichever" in text:
            return "Undefined"
        if "luna or kira" in text or ("luna" in text and "kira" in text):
            return "Luna or Kira"
        if "luna" in text:
            return "Luna"
        if "kira" in text:
            return "Kira"
        if "thor" in text:
            return "Thor"
        if "coco" in text:
            return "Coco"
        if "lola" in text:
            return "Lola"
        if "kitten" in text:
            return "Kittens"
        if "adult cat" in text or text == "cat":
            return "Adult cat"
        if "instagram" in text:
            return "Small dog (Instagram)"
        if "small dog" in text:
            return "Small dog"
        return "Other"


class StatusNormalizer:
    ADOPTION_MAP = {
        "approved": "approved",
        "aproved": "approved",
        "approved - reserved": "approved_reserved",
        "waitlist": "waitlist",
        "list b": "list_b",
        "list b (cats)": "list_b",
        "rejected": "rejected",
        "rejected - previous return": "rejected",
        "reuse": "reuse",
        "visit": "visit",
    }

    FOLLOWUP_MAP = {
        "handed over": "placed",
        "reserved": "reserved",
        "not collected": "not_collected",
        "returned": "returned",
        "returned (trial)": "returned_trial",
        "animal swap": "swapped",
        "waitlist": "waitlist",
    }

    @classmethod
    def adoption(cls, value: Any) -> str:
        text = _as_text(value).casefold()
        return cls.ADOPTION_MAP.get(text, "unknown")

    @classmethod
    def followup(cls, value: Any) -> str:
        text = _as_text(value).casefold()
        return cls.FOLLOWUP_MAP.get(text, "unknown")

    @staticmethod
    def adoption_label(canonical: str) -> str:
        return ADOPTION_STATUS_LABELS.get(canonical, canonical)

    @staticmethod
    def adoption_group(canonical: str) -> str:
        return ADOPTION_STATUS_GROUPS.get(canonical, "unknown")

    @staticmethod
    def followup_label(canonical: str) -> str:
        return FOLLOWUP_STATUS_LABELS.get(canonical, canonical)

    @staticmethod
    def followup_stage(value: Any) -> str:
        text = _as_text(value).casefold()
        if text == "6m ok":
            return "6m"
        if text == "1m ok":
            return "1m"
        if not text:
            return "none"
        return "unknown"


@dataclass
class NormalizedBundle:
    responses: pd.DataFrame
    scoring: pd.DataFrame
    final: pd.DataFrame
    followup: pd.DataFrame
    dob_audit: pd.DataFrame
    updated_audit: pd.DataFrame


class DataNormalizer:
    def __init__(self, bundle: DataBundle):
        self.bundle = bundle

    def _normalize_responses(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        df = self.bundle.responses.copy()
        df["is_test"] = (
            df["First name"].map(_as_text).str.casefold().eq("test")
            | df["Last name"].map(_as_text).str.casefold().eq("test")
        )
        df["name_norm"] = (
            df["First name"].map(NameNormalizer.key)
            + " "
            + df["Last name"].map(NameNormalizer.key)
        ).str.strip()
        df["first_name_norm"] = df["First name"].map(NameNormalizer.first)
        df["last_name_norm"] = df["Last name"].map(NameNormalizer.key)
        df["last_initial"] = df["Last name"].map(NameNormalizer.last_initial)
        phones = df["Phone"].map(PhoneNormalizer.normalize)
        df["phone_norm"] = [item[0] for item in phones]
        df["phone_format"] = [item[1] for item in phones]
        df["phone_is_placeholder"] = df["phone_norm"].map(
            PhoneNormalizer.is_placeholder
        )
        dobs = df["Date of birth"].map(DateNormalizer.parse)
        df["dob_parsed"] = [item[0] for item in dobs]
        df["dob_format"] = [item[1] for item in dobs]
        df["dob_ambiguous"] = [item[2] for item in dobs]
        df["dob_age_at_campaign"] = df["dob_parsed"].map(DateNormalizer.age_at)
        df["identity_type"] = df["Adopter no. or passport/licence"].map(
            IdentityNormalizer.classify
        )
        df["status_canon"] = df["Status"].map(StatusNormalizer.adoption)
        df["status_label"] = df["status_canon"].map(StatusNormalizer.adoption_label)
        df["status_group"] = df["status_canon"].map(StatusNormalizer.adoption_group)
        df["town_group"] = df["Town"].map(CategoryNormalizer.town)
        df["home_type"] = df["Home"].map(CategoryNormalizer.home_type)
        df["tenure"] = df["Home"].map(CategoryNormalizer.tenure)
        animals = df["Animals"].map(CategoryNormalizer.other_animals)
        df["other_animal_count"] = [item[0] for item in animals]
        df["other_animal_type"] = [item[1] for item in animals]
        df["other_animal_note"] = [item[2] for item in animals]
        df["source_group"] = df["How did you hear about us?"].map(
            CategoryNormalizer.source
        )
        df["animal_interest_group"] = df["Animal"].map(
            CategoryNormalizer.animal_interest
        )
        df["reviewer_name"] = df["Reviewed"].map(
            lambda value: REVIEWER_NAMES.get(_as_text(value), _as_text(value) or "No reviewer")
        )

        audit_rows: list[dict] = []
        for _, row in df.iterrows():
            raw = row["Date of birth"]
            expected, fmt, ambiguous = DateNormalizer.parse(raw)
            stored = row["dob_clean"]
            stored_ts = pd.to_datetime(stored, errors="coerce")
            mismatch = False
            if not pd.isna(expected) and not pd.isna(stored_ts):
                mismatch = expected.normalize() != stored_ts.normalize()
            audit_rows.append(
                {
                    "ID": row["ID"],
                    "raw_dob": raw,
                    "expected_dd_mm": expected,
                    "dob_clean": stored_ts,
                    "format": fmt,
                    "ambiguous": ambiguous,
                    "mismatch": mismatch,
                    "note": "Parser swaps day/month" if mismatch else "",
                }
            )
        dob_audit = pd.DataFrame(audit_rows)
        return df, dob_audit

    def _normalize_scoring(self) -> pd.DataFrame:
        df = self.bundle.scoring.copy()
        df["reviewer_name"] = df["Reviewer"].map(
            lambda value: REVIEWER_NAMES.get(_as_text(value), _as_text(value) or "No reviewer")
        )
        visit_numeric: list[float | None] = []
        visit_note: list[str] = []
        for value in df["Visit"]:
            if _is_missing(value):
                visit_numeric.append(None)
                visit_note.append("")
            elif isinstance(value, (int, float)):
                visit_numeric.append(float(value))
                visit_note.append("")
            else:
                text = _as_text(value)
                match = re.search(r"\b([1-5])\b", text)
                visit_numeric.append(float(match.group(1)) if match else None)
                visit_note.append(text)
        df["visit_numeric"] = visit_numeric
        df["visit_note"] = visit_note
        for column in ["Call", "Fit"]:
            df[f"{column.lower()}_numeric"] = pd.to_numeric(
                df[column], errors="coerce"
            )
        df["score_average"] = df[["call_numeric", "visit_numeric", "fit_numeric"]].mean(
            axis=1, skipna=True
        )
        return df

    def _normalize_final(self) -> pd.DataFrame:
        df = self.bundle.final.copy()
        df["name_norm"] = df["Full name"].map(NameNormalizer.key)
        df["status_canon"] = df["Status"].map(StatusNormalizer.adoption)
        df["status_label"] = df["status_canon"].map(StatusNormalizer.adoption_label)
        df["email_sent"] = (
            df["Email sent"].map(_as_text).replace({"": "unknown"}).str.title()
        )
        return df

    def _normalize_followup(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        df = self.bundle.followup.copy()
        phones = df["followup_phone"].map(PhoneNormalizer.normalize)
        df["phone_norm"] = [item[0] for item in phones]
        df["phone_format"] = [item[1] for item in phones]
        df["adopter_first"] = df["adopter"].map(NameNormalizer.first)
        df["adopter_last_initial"] = df["adopter"].map(NameNormalizer.last_initial)
        df["status_canon"] = df["status"].map(StatusNormalizer.followup)
        df["status_label"] = df["status_canon"].map(StatusNormalizer.followup_label)
        df["followup_stage"] = df["followup"].map(StatusNormalizer.followup_stage)
        df["animal_swap_bool"] = (
            df["animal_swap"].map(_as_text).str.casefold().eq("yes")
        )

        audit_rows: list[dict] = []
        for _, row in df.iterrows():
            raw = _as_text(row["updated"])
            parsed = pd.to_datetime(raw, format="%d-%b", errors="coerce")
            if pd.isna(parsed):
                parsed = pd.to_datetime(raw, dayfirst=True, errors="coerce")
            audit_rows.append(
                {
                    "animal_code": row["animal_code"],
                    "adopter": row["adopter"],
                    "updated_raw": raw,
                    "day": parsed.day if not pd.isna(parsed) else None,
                    "month": parsed.month if not pd.isna(parsed) else None,
                    "month_label": parsed.strftime("%b") if not pd.isna(parsed) else "",
                    "year_missing": True if not pd.isna(parsed) else False,
                }
            )
        updated_audit = pd.DataFrame(audit_rows)
        return df, updated_audit

    def normalize(self) -> NormalizedBundle:
        responses, dob_audit = self._normalize_responses()
        scoring = self._normalize_scoring()
        final = self._normalize_final()
        followup, updated_audit = self._normalize_followup()
        return NormalizedBundle(
            responses=responses,
            scoring=scoring,
            final=final,
            followup=followup,
            dob_audit=dob_audit,
            updated_audit=updated_audit,
        )
