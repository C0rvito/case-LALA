from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "outputs"
TABLE_DIR = OUTPUT_DIR / "tables"
FIGURE_DIR = OUTPUT_DIR / "figures"
REPORT_PATH = OUTPUT_DIR / "eda_report.md"
FIGURE_MANIFEST_PATH = OUTPUT_DIR / "figure_manifest.csv"
FIGURE_QA_PATH = TABLE_DIR / "figure_qa.csv"
RUN_MANIFEST_PATH = OUTPUT_DIR / "run_manifest.json"

WORKBOOK_PATH = DATA_DIR / "03_team_a_adoptions_spring_2026.xlsx"
FOLLOWUP_PATH = DATA_DIR / "04_team_b_followup_animals.csv"
FORM_PATH = DATA_DIR / "02_instrument_form.md"

SHEETS = {
    "responses": "Responses",
    "scoring": "Scoring",
    "summary": "Summary",
    "sheet3": "Sheet3",
    "final": "final",
}

CAMPAIGN_START = "2026-03-01"
CAMPAIGN_END = "2026-04-10"

FIGURE_DPI = 200
MIN_FONT_SIZE = 9.0
MAX_CATEGORIES = 30

ADOPTION_STATUS_LABELS = {
    "approved": "Approved",
    "approved_reserved": "Approved — reserved",
    "waitlist": "Waitlist",
    "list_b": "List B",
    "rejected": "Rejected",
    "reuse": "Reuse",
    "visit": "Visit",
    "unknown": "Unknown",
}

ADOPTION_STATUS_ORDER = [
    "approved",
    "approved_reserved",
    "waitlist",
    "list_b",
    "reuse",
    "visit",
    "rejected",
    "unknown",
]

ADOPTION_STATUS_GROUPS = {
    "approved": "positive",
    "approved_reserved": "positive",
    "waitlist": "pending",
    "list_b": "pending",
    "reuse": "pending",
    "visit": "process",
    "rejected": "negative",
    "unknown": "unknown",
}

FOLLOWUP_STATUS_LABELS = {
    "placed": "Placed",
    "reserved": "Reserved",
    "not_collected": "Not collected",
    "returned": "Returned",
    "returned_trial": "Returned in trial",
    "swapped": "Animal swap",
    "waitlist": "Waitlist",
    "unknown": "Unknown",
}

FOLLOWUP_STATUS_ORDER = [
    "placed",
    "reserved",
    "not_collected",
    "returned",
    "returned_trial",
    "swapped",
    "waitlist",
    "unknown",
]

FOLLOWUP_STAGE_LABELS = {
    "6m": "6 months OK",
    "1m": "1 month OK",
    "none": "No follow-up",
}

REVIEWER_NAMES = {
    "MT": "Megan Tate",
    "GC": "Graham Cole",
    "JP": "Jas Patel",
}

STAGE_LABELS = {
    "estrutural": "Structural EDA",
    "qualidade": "Data quality",
    "semantica": "Semantic EDA",
}

PALETTE = {
    "primary": "#0F4C5C",
    "secondary": "#E36414",
    "teal": "#2A9D8F",
    "teal_light": "#7FB7A8",
    "amber": "#E9C46A",
    "blue": "#457B9D",
    "mauve": "#9A8C98",
    "red": "#B23A48",
    "red_light": "#D07A84",
    "orange": "#E36414",
    "grey": "#6C757D",
    "light_grey": "#D9D9D9",
    "very_light_grey": "#F1F3F5",
    "ink": "#1F2933",
    "muted": "#52606D",
    "white": "#FFFFFF",
}

ADOPTION_STATUS_COLORS = {
    "approved": PALETTE["teal"],
    "approved_reserved": PALETTE["teal_light"],
    "waitlist": PALETTE["amber"],
    "list_b": PALETTE["blue"],
    "reuse": PALETTE["mauve"],
    "visit": PALETTE["orange"],
    "rejected": PALETTE["red"],
    "unknown": PALETTE["light_grey"],
}

FOLLOWUP_STATUS_COLORS = {
    "placed": PALETTE["teal"],
    "reserved": PALETTE["amber"],
    "not_collected": PALETTE["orange"],
    "returned": PALETTE["red"],
    "returned_trial": PALETTE["red_light"],
    "swapped": PALETTE["blue"],
    "waitlist": PALETTE["mauve"],
    "unknown": PALETTE["light_grey"],
}

FOLLOWUP_STAGE_COLORS = {
    "6m": PALETTE["teal"],
    "1m": PALETTE["teal_light"],
    "none": PALETTE["light_grey"],
}

SHEET_COLORS = {
    "Responses": PALETTE["primary"],
    "Scoring": PALETTE["orange"],
    "Summary": PALETTE["mauve"],
    "Sheet3": PALETTE["grey"],
    "final": PALETTE["blue"],
    "Follow-up": PALETTE["teal"],
}

ISSUE_CATEGORY_COLORS = {
    "Structure": PALETTE["blue"],
    "Identity": PALETTE["orange"],
    "Status": PALETTE["teal"],
    "Time": PALETTE["mauve"],
    "Formula": PALETTE["red"],
    "Process": PALETTE["primary"],
}

FIGURE_STAGE_DIRS = {
    "estrutural": "estrutural",
    "qualidade": "qualidade",
    "semantica": "semantica",
}
