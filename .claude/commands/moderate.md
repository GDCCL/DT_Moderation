---
description: Run a moderation pass over a cohort, sampling across grade boundaries and updating the analytics DB
argument-hint: <module> <cohort>
---

You are running a moderation pass for the degree-apprenticeship moderation tool.

The user invoked: `/moderate $ARGUMENTS`

Parse `$ARGUMENTS` as two positional values:
- `$1` = module code (e.g. `DT604`)
- `$2` = cohort code (e.g. `Sep23`)

If either is missing, tell the user the expected form and stop.

## Working paths

- Brief:        `modules/$1/brief.*`   (one of `.pdf`, `.docx`, `.md`, `.txt`)
- Level rubric: `rubrics/L<level>.json` — level is the second digit of the module code (`DT4xx` → L4, `DT5xx` → L5, `DT6xx` → L6). Use `python3 scripts/rubric.py level $1` to derive it.
- Cohort:       `modules/$1/cohorts/$2/`
- Grades:       `modules/$1/cohorts/$2/grades.xlsx`

Stop and tell the user if any are missing.

## Grades xlsx schema (fixed)

Columns: `Name`, `ULN`, `PDE`, `Client`, `Status`, `Cohort`, `Part A`, `Part B` (optional — Part A-only modules omit it), `Total Calculation`, `Assessed By`, `Comments`, `Moderation sample?`, `Moderation Comments`.

- `Comments` is the **tutor's assessment feedback** — read it, don't overwrite.
- `Moderation sample?` is where you set `Y` on every sampled learner.
- `Moderation Comments` is where the moderator comment goes.
- `Total Calculation` is the figure to band on.

## Step 1 — Load module context, level rubric, and brief

1. Pull the catalogue entry:
   ```
   python3 scripts/programme.py module $1
   ```
   If the script errors, the module code is unknown — stop and tell the user the valid codes. Hold the returned record in working memory — you'll cite learning outcomes (`LO1`–`LO4`) and module challenges (`MCA`/`MCB`) by ID.

2. Load the level rubric:
   ```
   python3 scripts/rubric.py for-module $1
   ```
   This returns 10 criteria (the same names that appear in the module's `programmeLearningOutcomes` mapping) with descriptors for 7 bands: `Fail` / `Insufficient` / `Satisfactory` / `Good` / `Very Good` / `Excellent` / `Outstanding`. Keep these descriptors in working memory — every moderator comment cites them.

3. Read the brief.
   - `.pdf`, `.md`, `.txt`: use the Read tool directly.
   - `.docx`: convert via `pandoc <file> -t plain` or `python3 -c "from docx import Document; print('\n'.join(p.text for p in Document('<file>').paragraphs))"`.

   If neither docx path works, tell the user how to install one and stop.

4. **Map the module's LOs to rubric criteria.** Each LO in the catalogue has a `programmeLearningOutcomes` list; those names match the 10 rubric criteria 1-to-1 (treat case and hyphen differences leniently — e.g. `Creative Problem-Solving` and `Creative Problem Solving` are the same). Build a mental map `LO_id → [criterion, …]` for the module. You'll use it when forming moderator comments and tagging themes.

## Step 2 — Read the grades xlsx

```
python3 scripts/xlsx_io.py columns modules/$1/cohorts/$2/grades.xlsx
python3 scripts/xlsx_io.py rows    modules/$1/cohorts/$2/grades.xlsx <sheet>
```

Determine whether the module has Part B by checking the column list. Note which sheet name is in use.

## Step 3 — Sample across rubric bands

Bucket learners by `Total Calculation` using the rubric bands (`scripts/rubric.py band $1 <total>` returns the band for a percentage):
- **Outstanding**: >85
- **Excellent**: 70–85
- **Very Good**: 60–69
- **Good**: 50–59
- **Satisfactory**: 40–49
- **Insufficient**: 32–39
- **Fail**: 0–31 (or non-numeric like `Refer`, `Fail`, `R`)

Skip rows where `Status` clearly indicates the learner shouldn't be moderated (withdrawn, deferred). Surface these as a separate list to the user.

Build a sample of **at least 6 learners** that spans every populated band — minimum one from each band, then top up from the most-populated bands until you reach 6. Prefer learners whose `Moderation Comments` cell is currently empty.

Show the sample plan to the user (names + bands + tutor) and **wait for confirmation** before writing anything to the xlsx.

## Step 4 — Moderate each sampled learner via the four-agent pipeline

Moderation must not "mark its own homework". For each sampled learner, you orchestrate four subagents with strict information firewalls:

```
       ┌──────────────────────────┐    ┌──────────────────────────┐
       │ Agent 1                  │    │ Agent 3                  │
       │ independent-assessor     │    │ feedback-auditor         │
       │  sees: brief, rubric,    │    │  sees: brief, rubric,    │
       │        learner work      │    │        tutor Comments    │
       │  must not see: tutor     │    │  must not see: learner   │
       │  grade/Comments          │    │  work, AI assessment     │
       └────────────┬─────────────┘    └────────────┬─────────────┘
                    │                               │
                    ▼                               │
       ┌──────────────────────────┐                 │
       │ Agent 2                  │                 │
       │ assessment-comparator    │                 │
       │  sees: Agent 1 output,   │                 │
       │        tutor grade,      │                 │
       │        tutor Comments    │                 │
       └────────────┬─────────────┘                 │
                    │                               │
                    └─────────────┬─────────────────┘
                                  ▼
                     ┌──────────────────────────┐
                     │ Agent 4                  │
                     │ moderation-writer        │
                     │  sees: Agent 2 + 3 out,  │
                     │        AI strengths/imps │
                     │  writes the xlsx         │
                     └──────────────────────────┘
```

You (the orchestrator) hold the full picture from the xlsx but only pass each agent the slice it's allowed to see. Agents 1 and 3 are independent — launch them in parallel (one tool-call message with two `Agent` invocations). Agents 2 and 4 are sequential.

### Per-learner orchestration

For each confirmed learner, with row index `R`:

1. **Locate the learner folder.** `modules/$1/cohorts/$2/<Learner Name>/`. If missing or empty, note it and skip — do not run any agents.

2. **Compute the tutor's band** from `Total Calculation`:
   ```
   python3 scripts/rubric.py band $1 <total>
   ```

3. **Launch Agent 1 and Agent 3 in parallel** (one message, two `Agent` tool calls):

   - `subagent_type: "independent-assessor"`, prompt containing:
     - Module code `$1`
     - Learner folder path `modules/$1/cohorts/$2/<Learner Name>/`
     - Brief path `modules/$1/brief.*`
     - Rubric path `rubrics/L<level>.json`
     - The module catalogue JSON (from `scripts/programme.py module $1`)
     - **Explicitly do not** include the tutor's `Total Calculation`, `Comments`, or any pre-existing `Moderation Comments`.

   - `subagent_type: "feedback-auditor"`, prompt containing:
     - Module code `$1`
     - The tutor's `Comments` text verbatim
     - Brief path
     - Rubric path
     - The module catalogue JSON
     - **Explicitly do not** include the learner folder path or the AI assessment.

4. **Launch Agent 2** once Agent 1 returns. `subagent_type: "assessment-comparator"`, prompt containing:
   - The full Agent 1 JSON output
   - Tutor `Total Calculation` (numeric)
   - Tutor band (from Step 4.2)
   - Tutor `Comments` text

5. **Launch Agent 4** once both Agent 2 and Agent 3 have returned. `subagent_type: "moderation-writer"`, prompt containing:
   - `xlsx_path`: `modules/$1/cohorts/$2/grades.xlsx`
   - `sheet`: the working sheet name
   - `row`: `R`
   - `module_code`: `$1`
   - The Agent 2 JSON output (comparator)
   - The Agent 3 JSON output (feedback auditor)
   - From Agent 1: just the `strengths`, `improvements`, `general_feedback`, and `human_review_flags` arrays (NOT the full criterion ratings — Agent 2 already distilled those)

6. **Retain** Agent 1's full JSON and Agent 2's verdict in your working notes — you'll need them for Step 5 (overall summary) and Step 6 (DB payload).

7. **Optional persistence.** Save Agent 1's full output to `modules/$1/cohorts/$2/<Learner Name>/ai_assessment.json` (the folder is gitignored, so this stays local). Provides a paper trail if the moderation is later audited.

If any agent fails or returns malformed JSON, surface the error to the user, skip the xlsx write for that learner, and continue with the next.

## Step 5 — Overall module moderation summary

After all sampled learners are processed, write an overall summary into the xlsx. Use a sheet named `Moderation Summary` if one exists; otherwise ask the user where it should go (new sheet, dedicated cell, or appended row) before writing.

Cover:
- Sample size and grade-band distribution
- Overall agreement / disagreement with tutor grading
- Any systemic patterns (e.g. distinctions under-evidenced against criterion X)
- Learners flagged for human review (video/audio, missing work, borderline cases)

Keep the summary anonymised — refer to learners by band or count, not by name.

## Step 6 — Update the analytics DB

This step is mandatory and runs after the xlsx is updated.

1. Verify the analytics DB is initialised. If `analytics.db` or `.env` is missing, tell the user to run `python3 scripts/db.py init` and stop.

2. Build a JSON payload covering **every** learner in the cohort (not just sampled ones — full cohort gives proper band distributions). For sampled learners, include the AI percentage / band / comparator verdict drawn from Agents 1 and 2. Shape:
   ```json
   {
     "module_code": "$1",
     "cohort_code": "$2",
     "overall_summary": "<the Step 5 summary, anonymised>",
     "learners": [
       {"uln": "<ULN as string>", "part_a": 65, "part_b": 70,
        "total": 67.5, "band": "Very Good", "was_sampled": true,
        "ai_percentage": 64.0, "ai_band": "Very Good",
        "verdict": "endorse"}
     ],
     "themes": [
       {"theme": "<short kebab-case label>", "count": <n>,
        "lo_id": "LO2",
        "notes": "<one-line explanation, anonymised>"}
     ]
   }
   ```

   - Omit `part_b` for Part A-only modules.
   - Skip learners with no ULN (warn the user).
   - `ai_percentage`, `ai_band`, `verdict`: include for sampled learners only (leave null for the rest).
   - `verdict` values come from the comparator: `endorse` / `endorse-with-note` / `escalate`.
   - Themes are short labels keyed to rubric criteria, e.g. `critical-thinking-strong`, `digital-proficiency-thin`, `professionalism-evidenced-via-collaboration`, or cross-cutting patterns like `tutor-under-marking-very-good-band`. Aim for 3–8 themes total, with `count` reflecting how many sampled learners showed each. Draw themes from the comparator's `criteria_disagreements` and the auditor's `issues`.
   - **Set `lo_id`** to the relevant LO (`LO1`–`LO4`) for the module when the theme maps to a criterion that the LO exercises (use the LO → criterion map from Step 1.4). Omit `lo_id` for cross-cutting themes (e.g. tutor-level patterns).

3. Pipe the payload to the DB script:
   ```
   echo '<payload>' | python3 scripts/db.py record-pass
   ```
   Or write the payload to a temp file and `cat` it in — whichever is cleaner.

4. Report the `pass_id` returned by the script.

## Step 7 — Final report to the user

Tell the user:
- Which learners were sampled and from which bands
- A one-line moderation outcome per sampled learner
- Where the overall summary lives in the xlsx
- The analytics `pass_id` and how many learners + themes were recorded
- Anything that needs follow-up

Remind the user that `analytics.db` has changed locally — to share the new pass with collaborators they should:
```
git add analytics.db && git commit -m "Moderation pass: $1 $2" && git push
```
Do not run those commands yourself. The grades xlsx and learner folders are gitignored and stay local.
