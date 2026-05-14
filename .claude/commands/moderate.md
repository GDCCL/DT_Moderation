---
description: Run a moderation pass over a cohort, sampling across grade boundaries
argument-hint: <module> <cohort>
---

You are running a moderation pass for the degree-apprenticeship moderation tool.

The user invoked: `/moderate $ARGUMENTS`

Parse `$ARGUMENTS` as two positional values:
- `$1` = module code (e.g. `DT604`)
- `$2` = cohort code (e.g. `Sep23`)

If either is missing, tell the user the expected form and stop.

## Working paths

- Brief:   `modules/$1/brief.*`   (one of `.pdf`, `.docx`, `.md`, `.txt`)
- Rubric:  `modules/$1/rubric.*`
- Cohort:  `modules/$1/cohorts/$2/`
- Grades:  `modules/$1/cohorts/$2/grades.xlsx`

Stop and tell the user if any of these are missing.

## Step 1 — Load module context

Read the brief and rubric. Keep both in working memory for every learner you assess.

- `.pdf`, `.md`, `.txt`: use the Read tool directly.
- `.docx`: convert first via either:
  - `pandoc <file> -t plain` (preferred if available), or
  - `python3 -c "from docx import Document; print('\n'.join(p.text for p in Document('<file>').paragraphs))"`

If neither works, tell the user how to install one and stop.

## Step 2 — Inspect the grades xlsx

```
python3 scripts/xlsx_io.py columns modules/$1/cohorts/$2/grades.xlsx
```

Identify these columns:
- **Learner name** (required)
- **Grade / mark** (required — usually a number 0–100, sometimes a band label)
- **Tutor feedback** (optional, read-only — never overwrite)
- **Moderator comment** (where you will write per-learner moderation feedback)

If any required column is ambiguous, ask the user before proceeding. If no moderator-comment column exists, ask whether to add one (and what header to use) before doing so.

## Step 3 — Sample across grade boundaries

```
python3 scripts/xlsx_io.py rows modules/$1/cohorts/$2/grades.xlsx <sheet>
```

Bucket learners by grade band:
- **Distinction**: 70+
- **Merit**: 60–69
- **Pass (upper)**: 50–59
- **Pass (lower)**: 40–49
- **Refer / Fail**: < 40 or non-numeric (`Refer`, `Fail`, `R`)

Build a sample of **at least 6 learners** that spans every populated band — minimum one from each band, then top up from the most-populated bands until you reach 6. Prefer learners whose moderator-comment cell is currently empty.

Show the sample plan to the user (names + bands) and **wait for confirmation** before writing anything to the xlsx.

## Step 4 — Moderate each sampled learner

For each confirmed learner, in order:

1. Locate `modules/$1/cohorts/$2/<Learner Name>/`. If the folder is missing or empty, note this and skip — do not invent content.

2. Walk the learner folder. Handle by type:
   - `.pdf`, `.md`, `.txt`, source code: read directly.
   - `.docx`: convert as in Step 1.
   - `.xlsx`: dump with `python3 scripts/xlsx_io.py columns ...` then `rows ...`.
   - `.mp4`, `.mov`, `.wav`, `.mp3`: **do not attempt to read.** Add to this learner's "needs human review" list and call it out in the moderator comment.
   - Git repos / nested project folders: read the README first, then sample top-level source files. Don't try to read every file.

3. Read any tutor assessment-feedback file in the learner folder (commonly `feedback.docx`, `feedback.md`, or similar). Use it as context but form your own view independently. Tutor feedback may also live in a column of the grades xlsx — read that too.

4. Assess the work against the brief and rubric. Decide whether the awarded grade is defensible against rubric criteria. Cite specific criteria.

5. Write the moderator comment into the xlsx:
   ```
   python3 scripts/xlsx_io.py set modules/$1/cohorts/$2/grades.xlsx <sheet> <row> <column> "<comment>"
   ```
   The comment must:
   - State whether you agree with the grade band, with one-line rationale.
   - Cite at least one rubric criterion that supports the call.
   - Flag any video/audio artefacts that need human review.
   - Stay concise — target 80–150 words.

## Step 5 — Overall module moderation summary

After all sampled learners are processed, write an overall summary. If the workbook has a sheet named like `Moderation Summary` / `Overall` / similar, use it. Otherwise ask the user where it should go (new sheet, dedicated cell, etc.) before writing.

The summary should cover:
- Sample size and grade-band distribution
- Overall agreement / disagreement with tutor grading
- Any systemic patterns across the cohort (e.g. distinctions under-evidenced against criterion X)
- A list of learners flagged for human review (video/audio, missing work, borderline cases)

## Step 6 — Report to chat

Tell the user:
- Which learners were sampled and from which bands
- A one-line moderation outcome per learner
- Where the overall summary lives in the xlsx
- Anything that needs follow-up

Do not commit anything. The grades xlsx and learner folders are gitignored.
