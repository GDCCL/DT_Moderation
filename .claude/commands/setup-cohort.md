---
description: Pre-flight check that a cohort is ready to moderate (no filesystem writes)
argument-hint: <module> <cohort>
---

You are running a pre-flight check for the degree-apprenticeship moderation tool.

The user invoked: `/setup-cohort $ARGUMENTS`

Parse `$ARGUMENTS` as two positional values:
- `$1` = module code (e.g. `DT604`)
- `$2` = cohort code (e.g. `Sep23`)

If either is missing, tell the user the expected form and stop.

This command **reads only** — it must not create, move, rename, or delete any files. Its job is to surface mismatches before the moderator runs `/moderate`.

## Working paths

- Module folder:   `modules/$1/`
- Brief:           `modules/$1/brief.*`   (one of `.pdf`, `.docx`, `.md`, `.txt`)
- Level rubric:    `rubrics/L<level>.json` where level = `4` / `5` / `6` based on the second digit of the module code (`DT4xx` → L4, `DT5xx` → L5, `DT6xx` → L6)
- Cohort folder:   `modules/$1/cohorts/$2/`
- Grades:          `modules/$1/cohorts/$2/grades.xlsx`

## Expected xlsx columns

`Name`, `ULN`, `PDE`, `Client`, `Status`, `Cohort`, `Part A`, `Part B`, `Total Calculation`, `Assessed By`, `Comments`, `Moderation sample?`, `Moderation Comments`.

`Part B` is **optional** — some modules are Part A only. Every other column is required.

## Checks

Run all of these, then report a single consolidated readiness summary at the end.

1. **Module code is in the programme catalogue.** Run:
   ```
   python3 scripts/programme.py module $1
   ```
   If it errors, the code is unknown — tell the user the valid codes (the script lists them on failure) and stop. On success, hold the module's `title`, `moduleChallenge` and `learningOutcomes` in context for later steps.

2. **Module folder exists.** Otherwise: not ready, tell the user to create `modules/$1/`.

3. **Brief present.** Look for `brief.*` in the module folder. If missing or there are multiple candidates with the same stem, call it out. (There's no per-module rubric — the level rubric is centralised.)

4. **Level rubric present.** Run `python3 scripts/rubric.py level $1` to get the level. Verify `rubrics/L<level>.json` exists. If missing, not ready.

5. **Cohort folder exists.** Otherwise: not ready.

6. **Grades xlsx exists.** Otherwise: not ready.

7. **Inspect the xlsx:**
   ```
   python3 scripts/xlsx_io.py columns modules/$1/cohorts/$2/grades.xlsx
   ```
   Verify every required column is present (header match is case-sensitive — flag any case/spacing variant). Cross-check the xlsx structure against the module catalogue: the catalogue lists how many module challenges the module has (most have MCA + MCB; some are MCA only). If the xlsx is missing `Part B` but the catalogue says the module has an MCB, flag it; conversely flag a stray `Part B` column for a Part-A-only module.

8. **Read learner rows:**
   ```
   python3 scripts/xlsx_io.py rows modules/$1/cohorts/$2/grades.xlsx <sheet>
   ```
   Extract trimmed `Name` and `ULN` from each non-empty row. Skip rows where both are blank. Flag any row where `Name` is present but `ULN` is missing — `ULN` is required for the analytics DB.

9. **List learner folders** directly under `modules/$1/cohorts/$2/` (subdirectories only, ignoring `grades.xlsx` and any other files at the cohort root).

10. **Match xlsx names against folder names.** Report:
    - Names in xlsx with **no matching folder** (case-insensitive, whitespace-collapsed match).
    - Folders with **no matching xlsx row**.
    - **Near-miss pairs** that look like typos (one extra letter, swapped surname/forename order, etc.) — suggest the likely intended match but do not rename anything.

11. **Empty folders.** For each learner folder that matched an xlsx row, note if it appears to contain no submission files at all.

12. **Analytics DB salt.** Verify `.env` exists at the repo root and contains a non-empty `MODERATION_HASH_SALT`. If missing, tell the user to run:
    ```
    python3 scripts/db.py init
    ```
    and to share the resulting salt with collaborators out of band so hashes match across machines.

## Output

Finish with a clear verdict, e.g.:

> **Ready to moderate.** `DT604 — Project Report` (L6, MCA 50% + MCB 50%). 18 learners matched. Brief, L6 rubric, grades xlsx, and salt all present.

or

> **Not ready.** 3 issues:
> - Brief missing in `modules/DT604/`.
> - 1 xlsx name has no folder: `Priya Patel` (closest folder: `Priya Patel-Smith`?).
> - 2 rows have no ULN — analytics will skip them.

Do not commit anything. Do not modify any files.
