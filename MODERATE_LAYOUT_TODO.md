# `/moderate` layout flexibility — TODO

Captured during the DT604 / `Sep 23` pre-flight on 2026-05-14. The cohort on
disk is healthy but the file naming diverges from the README's documented
layout in several places. Rather than reorganise every cohort an assessor
ever saves, the toolkit should tolerate the natural way these files arrive.

This document is the spec for that future change. No code has been written.

---

## Tolerances to add

Each item below lists the **current expectation** and the **tolerance to add**.
File pointers under "Likely lands in" are starting points — the implementer
should check first.

### 1. Brief lives inside the cohort folder, not the module root

- **Today:** `modules/<MOD>/brief.{pdf|docx|md|txt}`.
- **Tolerate:** any file matching `*[Bb]rief*.{pdf,docx,md,txt}` either in
  `modules/<MOD>/` or in `modules/<MOD>/cohorts/<COHORT>/`. If both exist,
  prefer the module-root copy (it applies to every cohort); if only the
  cohort copy exists, use it.
- **Likely lands in:** `.claude/commands/setup-cohort.md`,
  `.claude/commands/moderate.md`.
- **Real example:**
  `modules/DT604/cohorts/Sep 23/DT604 Module Challenge Brief V1 Sep 23.pdf`.

### 2. Grades file isn't called `grades.xlsx`

- **Today:** `modules/<MOD>/cohorts/<COHORT>/grades.xlsx`.
- **Tolerate:** any `*.xlsx` directly in the cohort folder. If more than one,
  prefer the one whose filename contains "Grade" (case-insensitive).
- **Likely lands in:** `.claude/commands/setup-cohort.md`,
  `.claude/commands/moderate.md`.
- **Real example:** `DT604 DTSP Learner Grades.xlsx`.

### 3. Cohort code can contain spaces

- **Today:** README example is `Sep23` — no whitespace.
- **Tolerate:** anything the user passes as the second positional arg,
  including embedded spaces (e.g. `Sep 23`). Every path use must be quoted.
- **Likely lands in:** All three command markdowns (`setup-cohort`,
  `moderate`, `analytics`).
- **Test:** `/setup-cohort DT604 "Sep 23"` must work without renaming the
  folder.

### 4. Workbook has multiple sheets; data isn't always on the first

- **Today:** `scripts/xlsx_io.py rows <file> <sheet>` already takes a sheet
  name, but the commands don't pick the right one — they assume a single
  sheet or hardcode a name.
- **Tolerate:** auto-detect the data sheet. Pick the one whose header row
  contains both `Name` and `ULN`. If multiple qualify, prefer the one whose
  sheet name contains "Learner" or "Grade".
- **Likely lands in:** `.claude/commands/moderate.md`,
  `.claude/commands/setup-cohort.md` (use the existing `xlsx_io.py columns`
  output to pick a sheet before calling `rows`).
- **Real example:** Workbook has `Moderation Report` and
  `Learners & Grades`; only the second has data.

### 5. Column headers may have stray whitespace

- **Today:** Header lookup is case-sensitive and exact; `"Moderation sample? "`
  (trailing space) ≠ `"Moderation sample?"`.
- **Tolerate:** strip leading/trailing whitespace when **matching** a header.
  When **writing back**, preserve the original cell header verbatim so we
  don't change the assessor's file shape.
- **Likely lands in:** `scripts/xlsx_io.py` (both the row reader and the cell
  writer used by Agent 4 / `moderation-writer`).
- **Real example:** `"Moderation sample? "` in the DT604 xlsx.

### 6. Learner folders are prefixed with the ULN

- **Today:** `modules/<MOD>/cohorts/<COHORT>/<Learner Name>/`.
- **Tolerate:** `<ULN> - <Learner Name>/` (10-digit ULN, space-hyphen-space,
  then the name). Also still accept bare `<Name>/`.
- **Matching strategy:**
  1. Primary — match by **ULN prefix**: folder name starts with the 10-digit
     ULN from the xlsx row.
  2. Fallback — match by name suffix: strip a leading `<10 digits> - ` and
     compare what's left case-insensitively against the xlsx `Name`,
     normalising whitespace.
- **Likely lands in:** `.claude/commands/setup-cohort.md` (the name/folder
  cross-check), `.claude/commands/moderate.md` (locating each learner's
  submission folder).
- **Real example:** `4213670979 - Adam Gray/`.

### 7. Stop reading xlsx rows at the end of the learner block

- **Today:** Every non-empty row is treated as a learner. The DT604 xlsx has
  a "Grade Distribution" stats grid below the data (rows 22+) that bleeds
  into the rows reader's output and would corrupt the band distribution and
  sampling.
- **Tolerate:** treat a row as a learner only if `ULN` is a 10-digit integer
  **and** `Name` is a non-empty string. Stop at the first row that fails
  this test (or, more robustly, skip any row that fails and don't sample it).
- **Likely lands in:** `.claude/commands/moderate.md` and
  `.claude/commands/setup-cohort.md` (the row-filter step). Could also be a
  helper in `scripts/xlsx_io.py` exposed as e.g.
  `xlsx_io.py learner-rows <file>` that applies the filter for both commands.
- **Real example:** rows 22–43 of the DT604 xlsx contain Mode/Mean/Std-Dev
  and a Grade Distribution table.

### 8. Ignore the in-sheet `Cohort` column entirely

- **Today:** `/setup-cohort` flags rows whose `Cohort` value doesn't match
  the cohort arg.
- **Tolerate:** don't cross-check this column. Cohort identity comes from
  the path arg, not from a free-text cell that assessors sometimes fat-finger
  (e.g. `Sept 2024`, `Sept 2026` mixed in with `Sept 2023`).
- **Likely lands in:** `.claude/commands/setup-cohort.md`.

---

## Where each change likely lands

| # | Tolerance | Files |
|---|---|---|
| 1 | Brief fallback to cohort folder | `.claude/commands/setup-cohort.md`, `.claude/commands/moderate.md` |
| 2 | Grades file glob | `.claude/commands/setup-cohort.md`, `.claude/commands/moderate.md` |
| 3 | Cohort code with spaces | All three command markdowns |
| 4 | Sheet auto-detect | `.claude/commands/moderate.md`, `.claude/commands/setup-cohort.md` |
| 5 | Header whitespace tolerance | `scripts/xlsx_io.py` |
| 6 | ULN-prefix folder names | `.claude/commands/setup-cohort.md`, `.claude/commands/moderate.md` |
| 7 | Stop at non-learner rows | `.claude/commands/moderate.md`, `.claude/commands/setup-cohort.md` (or a new `scripts/xlsx_io.py learner-rows`) |
| 8 | Skip Cohort-column cross-check | `.claude/commands/setup-cohort.md` |

---

## Test plan

Run these after implementing each tolerance:

1. `/setup-cohort DT604 "Sep 23"` reports **Ready** (currently Not Ready).
2. `/moderate DT604 "Sep 23"`:
   - Finds the brief inside the cohort folder.
   - Picks `Learners & Grades` as the data sheet.
   - Reads exactly 18 learner rows; skips the stats block at rows 22+.
   - Matches all 18 xlsx names to their `<ULN> - <Name>/` folders.
   - Writes `Y` flags and moderator comments back to the `Moderation sample? `
     and `Moderation Comments` columns of the original xlsx (no rename, no
     move).
   - Doesn't choke on Jermaine Dallas (`Cohort: Sept 2024`) or Joshua Aptroot
     (`Cohort: Sept 2026`).
3. **Regression:** a cohort that does follow the README convention
   (`grades.xlsx`, bare `<Name>/` folders, `brief.pdf` at module root, no
   trailing space in headers) must still pass `/setup-cohort` and
   `/moderate`.

---

## Also do at the same time

- Update `README.md` to describe the relaxed conventions so future
  collaborators know either layout is fine.
- Consider whether `Status != "Active"` rows should be skipped from sampling
  (e.g. withdrawn learners) — separate from the row-filter above, this is a
  domain decision, not a layout one.

## Out of scope

- The xlsx's own band thresholds (`0-34 / 35-39 / 40-49 / …`) don't match
  the toolkit's `Fail 0-31 / Insufficient 32-39 / …`. That's a different
  problem (boundary alignment, not layout) and belongs in its own TODO.
- Renaming/moving any existing cohort files. The whole point of this work
  is that we don't have to.
