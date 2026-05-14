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
- Rubric:          `modules/$1/rubric.*`
- Cohort folder:   `modules/$1/cohorts/$2/`
- Grades:          `modules/$1/cohorts/$2/grades.xlsx`

## Expected xlsx columns

`Name`, `ULN`, `PDE`, `Client`, `Status`, `Cohort`, `Part A`, `Part B`, `Total Calculation`, `Assessed By`, `Comments`, `Moderation sample?`, `Moderation Comments`.

`Part B` is **optional** — some modules are Part A only. Every other column is required.

## Checks

Run all of these, then report a single consolidated readiness summary at the end.

1. **Module folder exists.** Otherwise: not ready, tell the user to create it.

2. **Brief and rubric present.** Look for `brief.*` and `rubric.*` in the module folder. If either is missing, or there are multiple candidates with the same stem, call it out.

3. **Cohort folder exists.** Otherwise: not ready.

4. **Grades xlsx exists.** Otherwise: not ready.

5. **Inspect the xlsx:**
   ```
   python3 scripts/xlsx_io.py columns modules/$1/cohorts/$2/grades.xlsx
   ```
   Verify every required column is present (header match is case-sensitive — flag any case/spacing variant). Note whether `Part B` is present and report which mode the module is in (Part A only vs Part A+B).

6. **Read learner rows:**
   ```
   python3 scripts/xlsx_io.py rows modules/$1/cohorts/$2/grades.xlsx <sheet>
   ```
   Extract trimmed `Name` and `ULN` from each non-empty row. Skip rows where both are blank. Flag any row where `Name` is present but `ULN` is missing — `ULN` is required for the analytics DB.

7. **List learner folders** directly under `modules/$1/cohorts/$2/` (subdirectories only, ignoring `grades.xlsx` and any other files at the cohort root).

8. **Match xlsx names against folder names.** Report:
   - Names in xlsx with **no matching folder** (case-insensitive, whitespace-collapsed match).
   - Folders with **no matching xlsx row**.
   - **Near-miss pairs** that look like typos (one extra letter, swapped surname/forename order, etc.) — suggest the likely intended match but do not rename anything.

9. **Empty folders.** For each learner folder that matched an xlsx row, note if it appears to contain no submission files at all.

10. **Analytics DB salt.** Verify `.env` exists at the repo root and contains a non-empty `MODERATION_HASH_SALT`. If missing, tell the user to run:
    ```
    python3 scripts/db.py init
    ```
    and to share the resulting salt with collaborators out of band so hashes match across machines.

## Output

Finish with a clear verdict, e.g.:

> **Ready to moderate.** Part A + Part B module. 18 learners matched. Brief, rubric, grades xlsx, and salt all present.

or

> **Not ready.** 3 issues:
> - Rubric missing in `modules/DT604/`.
> - 1 xlsx name has no folder: `Priya Patel` (closest folder: `Priya Patel-Smith`?).
> - 2 rows have no ULN — analytics will skip them.

Do not commit anything. Do not modify any files.
