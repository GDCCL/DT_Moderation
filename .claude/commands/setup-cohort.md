---
description: Scaffold learner folders for a cohort, reading names from the grades xlsx
argument-hint: <module> <cohort>
---

You are setting up a cohort for the degree-apprenticeship moderation tool.

The user invoked: `/setup-cohort $ARGUMENTS`

Parse `$ARGUMENTS` as two positional values:
- `$1` = module code (e.g. `DT604`)
- `$2` = cohort code (e.g. `Sep23`)

If either is missing, tell the user the expected form and stop.

## Working paths

- Module folder:  `modules/$1/`
- Cohort folder:  `modules/$1/cohorts/$2/`
- Grades file:    `modules/$1/cohorts/$2/grades.xlsx`

## Steps

1. **Verify the module exists.** If `modules/$1/` is missing, stop and tell the user to create it and place `brief.*` and `rubric.*` inside before re-running.

2. **Verify the cohort folder exists.** Create `modules/$1/cohorts/$2/` if absent (the parent `cohorts/` directory is gitignored, so this is local-only).

3. **Verify the grades xlsx exists.** If `modules/$1/cohorts/$2/grades.xlsx` is missing, stop and ask the user to drop it in, then re-run. Do not invent grade data.

4. **Inspect the xlsx.** Run:
   ```
   python3 scripts/xlsx_io.py columns modules/$1/cohorts/$2/grades.xlsx
   ```
   This lists sheets and their column headers.

5. **Identify the learner-name column.** Look for a header like `Name`, `Learner`, `Learner Name`, `Student`, case-insensitively. If more than one candidate exists, or none, ask the user which column holds learner names before proceeding.

6. **Read the names:**
   ```
   python3 scripts/xlsx_io.py rows modules/$1/cohorts/$2/grades.xlsx <sheet>
   ```
   Extract the name field from each row. Trim whitespace. Skip blanks and any row that looks like a section header.

7. **Create a folder per learner** at `modules/$1/cohorts/$2/<Learner Name>/submission/`. Keep the natural-language form of the name (e.g. `Jane Doe`). Do not overwrite existing folders — if one is already there, leave it alone.

8. **Report a summary** to the user:
   - How many learner folders were created
   - How many already existed
   - Any names skipped (with the reason)
   - Reminder that learner submissions should now be placed inside each `submission/` folder

Do not commit anything. Submissions and the grades xlsx are gitignored on purpose.
