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

## Checks

Run all of these, then report a single consolidated readiness summary at the end.

1. **Module folder exists.** Otherwise: not ready, tell the user to create it.

2. **Brief and rubric present.** Look for `brief.*` and `rubric.*` in the module folder. If either is missing or there are multiple candidates with the same stem, call it out.

3. **Cohort folder exists.** Otherwise: not ready.

4. **Grades xlsx exists.** Otherwise: not ready.

5. **Inspect the xlsx:**
   ```
   python3 scripts/xlsx_io.py columns modules/$1/cohorts/$2/grades.xlsx
   ```
   Identify the learner-name column (`Name`, `Learner`, `Learner Name`, `Student`, case-insensitively). If ambiguous, ask the user which column holds learner names. Also note whether plausible columns exist for grade / mark and moderator comment — flag if either is absent.

6. **Read learner names:**
   ```
   python3 scripts/xlsx_io.py rows modules/$1/cohorts/$2/grades.xlsx <sheet>
   ```
   Extract the trimmed name from each non-empty row.

7. **List learner folders** directly under `modules/$1/cohorts/$2/` (subdirectories only, ignoring `grades.xlsx` and any other files at the cohort root).

8. **Match xlsx names against folder names.** Report:
   - Names in xlsx with **no matching folder** (case-insensitive, whitespace-collapsed match).
   - Folders with **no matching xlsx row**.
   - **Near-miss pairs** that look like typos (e.g. one extra letter, swapped surname/forename order) — suggest the likely intended match but do not rename anything.

9. **Empty folders.** For each learner folder that did match an xlsx row, note if it appears empty (no files of any type). The moderator may want to chase the learner.

## Output

Finish with a clear verdict, e.g.:

> **Ready to moderate.** 18 learners matched. Brief, rubric and grades xlsx all present.

or

> **Not ready.** 2 issues:
> - Rubric missing in `modules/DT604/`.
> - 1 xlsx name has no folder: `Priya Patel` (closest folder: `Priya Patel-Smith`?).

Do not commit anything. Do not modify any files.
