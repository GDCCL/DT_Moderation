---
description: Pre-flight check that a cohort is ready to moderate (no filesystem writes)
argument-hint: <module> <cohort>
---

You are running a pre-flight check for the degree-apprenticeship moderation tool.

The user invoked: `/setup-cohort $ARGUMENTS`

## Argument parsing

Parse `$ARGUMENTS` as exactly two positional values:
- `<module>` = the first whitespace-delimited token (e.g. `DT604`).
- `<cohort>` = everything after the first token, with leading and trailing whitespace trimmed. **May contain internal whitespace** (e.g. `Sep 23`, `January 2024`). Do not split it further.

If either is missing, tell the user the expected form (`/setup-cohort <module> <cohort>`) and stop.

Whenever you use these values in shell commands or paths, **double-quote** them so embedded spaces survive.

This command **reads only** — it must not create, move, rename, or delete any files. Its job is to surface mismatches before the moderator runs `/moderate`.

## Working paths

- Module folder:   `modules/<module>/`
- Brief:           preferred at `modules/<module>/brief.{pdf,docx,md,txt}`; if absent, accept any file matching `*[Bb]rief*.{pdf,docx,md,txt}` inside `modules/<module>/cohorts/<cohort>/`.
- Level rubric:    `rubrics/L<level>.json` where level = `4` / `5` / `6` based on the second digit of the module code (`DT4xx` → L4, `DT5xx` → L5, `DT6xx` → L6).
- Cohort folder:   `modules/<module>/cohorts/<cohort>/`
- Grades:          preferred at `modules/<module>/cohorts/<cohort>/grades.xlsx`; if absent, accept any `*.xlsx` directly in the cohort folder (prefer a filename containing `Grade` if multiple).

## Expected xlsx columns

`Name`, `ULN`, `PDE`, `Client`, `Status`, `Cohort`, `Part A`, `Part B`, `Total Calculation`, `Assessed By`, `Comments`, `Moderation sample?`, `Moderation Comments`.

`Part B` is **optional** — some modules are Part A only. Every other column is required.

Header matching is **whitespace-tolerant**: `"Moderation sample? "` (trailing space) is accepted as `Moderation sample?`. The xlsx_io helper handles this in both reads and writes; you should still flag stray whitespace as a minor warning so the user knows the underlying cell has it.

The in-sheet `Cohort` column is informational only — it's free-text that assessors sometimes fat-finger. **Do not** cross-check its values against the `<cohort>` arg.

## Checks

Run all of these, then report a single consolidated readiness summary at the end.

1. **Module code is in the programme catalogue.** Run:
   ```
   python3 scripts/programme.py module <module>
   ```
   If it errors, the code is unknown — tell the user the valid codes (the script lists them on failure) and stop. On success, hold the module's `title`, `moduleChallenge` and `learningOutcomes` in context for later steps. Note whether the module is Part A only (single MCA at 100%) or has both MCA and MCB.

2. **Module folder exists.** Otherwise: not ready, tell the user to create `modules/<module>/`.

3. **Brief present.** Look for `brief.{pdf,docx,md,txt}` in the module folder first. If none found there, fall back to globbing `modules/<module>/cohorts/<cohort>/*[Bb]rief*.{pdf,docx,md,txt}`. Report which location supplied the brief; if multiple candidates exist at either location, list them and pick the most-recently-modified.

4. **Level rubric present.** Run `python3 scripts/rubric.py level <module>` to get the level. Verify `rubrics/L<level>.json` exists. If missing, not ready.

5. **Cohort folder exists.** Otherwise: not ready. (Remember to quote the path — the cohort name may contain spaces.)

6. **Grades xlsx exists.** First try `modules/<module>/cohorts/<cohort>/grades.xlsx`. If absent, glob for `*.xlsx` directly in the cohort folder. If exactly one matches, use it. If multiple match, prefer one whose name contains `Grade` (case-insensitive); otherwise list all candidates and stop. Hold the resolved path for the next steps.

7. **Inspect the xlsx:**
   ```
   python3 scripts/xlsx_io.py columns "<grades_path>"
   ```
   Verify every required column is present (whitespace-tolerant match). Cross-check the xlsx structure against the module catalogue: if the xlsx is missing `Part B` but the catalogue says the module has an MCB, flag it; conversely flag a stray `Part B` column for a Part-A-only module. Flag stray header whitespace (e.g. `"Moderation sample? "`) as a minor warning — it doesn't block moderation but the user should know.

8. **Read learner rows:**
   ```
   python3 scripts/xlsx_io.py learner-rows "<grades_path>"
   ```
   The helper auto-picks the sheet whose header row contains both `Name` and `ULN` (preferring sheet names containing `Learner` or `Grade`), and only returns rows where `ULN` is a 10-digit integer and `Name` is non-empty. The output has the shape `{"sheet": "...", "headers": [...], "raw_headers": [...], "rows": [...]}`. Note the chosen sheet name and the raw headers — moderation will need both later.

   Extract trimmed `Name` and `ULN` from each row. Flag any row where ULN is missing (shouldn't happen after the filter, but in case the user pastes a Name without a ULN row above the stats block, surface it).

9. **List learner folders** directly under `modules/<module>/cohorts/<cohort>/` (subdirectories only, ignoring the xlsx and any other files at the cohort root).

10. **Match xlsx rows against folder names.** Folders may follow either convention:
    - `<Learner Name>/`  — the README default.
    - `<10-digit ULN> - <Learner Name>/`  — common when assessors pull from the SIS export.

    Matching strategy:
    1. **Primary — match by ULN.** A folder matches a row if its name starts with the row's `ULN` followed by ` - ` (space-hyphen-space) or if the folder is literally named just the ULN.
    2. **Fallback — match by name.** Strip any leading `<digits> - ` from the folder name. Compare the remainder to the row's `Name` case-insensitively with whitespace collapsed.

    Report:
    - Rows with **no matching folder** (case-insensitive, whitespace-collapsed).
    - Folders with **no matching xlsx row**.
    - **Near-miss pairs** that look like typos (one extra letter, swapped surname/forename order, etc.) — suggest the likely intended match but do not rename anything.

11. **Empty folders.** For each learner folder that matched an xlsx row, note if it appears to contain no submission files at all. EC/deferral comments in the xlsx (`Comments` column mentioning "EC", "extension", "deferred") usually explain these; surface them together.

12. **Analytics DB salt.** Verify `.env` exists at the repo root and contains a non-empty `MODERATION_HASH_SALT`. If missing, tell the user to run:
    ```
    python3 scripts/db.py init
    ```
    and to share the resulting salt with collaborators out of band so hashes match across machines.

## Output

Finish with a clear verdict, e.g.:

> **Ready to moderate.** `DT604 — End Point Assessment (Project Report)` (L6, MCA 100%). 18 learners matched. Brief (in cohort folder), L6 rubric, grades xlsx (`DT604 DTSP Learner Grades.xlsx`), and salt all present.

or

> **Not ready.** 3 issues:
> - Brief missing in both `modules/DT604/` and `modules/DT604/cohorts/Sep 23/`.
> - 1 xlsx name has no folder: `Priya Patel` (closest folder: `1234567890 - Priya Patel-Smith`?).
> - 2 rows have no ULN — analytics will skip them.

Do not commit anything. Do not modify any files.
