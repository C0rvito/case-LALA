# AGENTS.md

## Hard rule: `dont-touch/`

Never read, list, search, glob, edit, or otherwise access `dont-touch/` — directly
or through `bash` (e.g. `cat`, `grep`, `find`, scripts). Treat it as if it does
not exist. `opencode.json` enforces this; do not try to work around it or ask for
an exception.

## Project

Data case study for **Hearthway Rehoming Network** (Bristol centre). The brief
(`brief.md`) describes two teams — Adoptions and Follow-up — that each keep their
own records for the spring 2026 adoptions. The goal is a working prototype of a
shared record of adopters/households: link people across applications, adoptions,
returns, and re-adoptions, and support analysis of which screening signals predict
placements that last.

This is a Python data-analysis project, not an application server. Expect
notebook-style exploration and scripts that clean/merge the source files.

## Environment

- Python 3.13, managed with `uv` (`pyproject.toml`, `uv.lock`, `.venv/`).
- Dependencies: pandas, openpyxl, matplotlib, seaborn.
- Run commands through `uv`, e.g. `uv sync`, `uv run python script.py`.
- No test runner, linter, or formatter is configured.

## Layout

- `brief.md` — case context, teams, constraints, quotes.
- `data/` — source inputs:
  - `02_instrument_form.md` — adoption request form (markdown copy/screenshots).
  - `03_team_a_adoptions_spring_2026.xlsx` — Adoptions team spreadsheet (sheets:
    `Responses`, `Scoring`, `Summary`, `Sheet3`, `final`).
  - `04_team_b_followup_animals.csv` — Follow-up team list.
- `src/data/` — Python package (`data`) for the work; currently just
  `__init__.py`.
- `assets/` — supporting images.
- `dont-touch/` — off-limits (see hard rule above).

## Working notes

- Source data is messy and human-maintained: inconsistent statuses, initials as
  reviewer IDs, adopter names/phones as the only identifiers, mixed date formats.
  Preserve raw inputs; do transformations in `src/data/` or new scripts.
- Prefer deterministic, reproducible scripts over manual spreadsheet edits.
- Document assumptions about record linkage (name/phone/adopter number) in code
  or a short note.
