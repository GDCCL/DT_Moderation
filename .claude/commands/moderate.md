---
description: Run a moderation pass over a cohort, sampling across grade boundaries and updating the analytics DB
argument-hint: <module> <cohort>
---

You are running a moderation pass for the degree-apprenticeship moderation tool.

The user invoked: `/moderate $ARGUMENTS`

## Argument parsing

Parse `$ARGUMENTS` as exactly two positional values:
- `<module>` = the first whitespace-delimited token (e.g. `DT604`).
- `<cohort>` = everything after the first token, with leading and trailing whitespace trimmed. **May contain internal whitespace** (e.g. `Sep 23`, `January 2024`). Do not split it further.

If either is missing, tell the user the expected form (`/moderate <module> <cohort>`) and stop.

Whenever you use these values in shell commands or paths, **double-quote** them so embedded spaces survive.

## Working paths

- Brief:        preferred at `modules/<module>/brief.{pdf,docx,md,txt}`; if absent, accept any file matching `*[Bb]rief*.{pdf,docx,md,txt}` inside `modules/<module>/cohorts/<cohort>/`. If multiple candidates exist, pick the most-recently-modified.
- Level rubric: `rubrics/L<level>.json` — level is the second digit of the module code (`DT4xx` → L4, `DT5xx` → L5, `DT6xx` → L6). Use `python3 scripts/rubric.py level <module>` to derive it.
- Cohort:       `modules/<module>/cohorts/<cohort>/`
- Grades:       preferred at `modules/<module>/cohorts/<cohort>/grades.xlsx`; if absent, glob for `*.xlsx` directly in the cohort folder (prefer a filename containing `Grade` if multiple).

Resolve all four paths upfront and hold them in working memory. Stop and tell the user if any are missing.

## Grades xlsx schema

Columns: `Name`, `ULN`, `PDE`, `Client`, `Status`, `Cohort`, `Part A`, `Part B` (optional — Part A-only modules omit it), `Total Calculation`, `Assessed By`, `Comments`, `Moderation sample?`, `Moderation Comments`.

- `Comments` is the **tutor's assessment feedback** — read it, don't overwrite.
- `Moderation sample?` is where you set `Y` on every sampled learner.
- `Moderation Comments` is where the moderator comment goes.
- `Total Calculation` is the figure to band on.

Header matching is **whitespace-tolerant** — `"Moderation sample? "` (trailing space) is treated the same as `Moderation sample?`. The `xlsx_io.py set` command handles the trimming when matching column headers; you don't need to special-case it.

The in-sheet `Cohort` column is informational — do **not** cross-check it against `<cohort>`.

## Step 1 — Load module context, level rubric, and brief

1. Pull the catalogue entry:
   ```
   python3 scripts/programme.py module <module>
   ```
   If the script errors, the module code is unknown — stop and tell the user the valid codes. Hold the returned record in working memory — you'll cite learning outcomes (`LO1`–`LO4`) and module challenges (`MCA`/`MCB`) by ID. Note whether the module is Part A only.

2. Load the level rubric:
   ```
   python3 scripts/rubric.py for-module <module>
   ```
   This returns 10 criteria (the same names that appear in the module's `programmeLearningOutcomes` mapping) with descriptors for 7 bands: `Fail` / `Insufficient` / `Satisfactory` / `Good` / `Very Good` / `Excellent` / `Outstanding`. Keep these descriptors in working memory — every moderator comment cites them.

3. Read the brief from the resolved path (module-root preferred, cohort-folder fallback).
   - `.pdf`, `.md`, `.txt`: use the Read tool directly.
   - `.docx`: convert via `pandoc "<file>" -t plain` or `python3 -c "from docx import Document; print('\n'.join(p.text for p in Document('<file>').paragraphs))"`.

   If neither docx path works, tell the user how to install one and stop.

4. **Map the module's LOs to rubric criteria.** Each LO in the catalogue has a `programmeLearningOutcomes` list; those names match the 10 rubric criteria 1-to-1 (treat case and hyphen differences leniently — e.g. `Creative Problem-Solving` and `Creative Problem Solving` are the same). Build a mental map `LO_id → [criterion, …]` for the module. You'll use it when forming moderator comments and tagging themes.

## Step 2 — Read the grades xlsx

```
python3 scripts/xlsx_io.py learner-rows "<grades_path>"
```

The helper auto-detects the data sheet (one whose header row contains both `Name` and `ULN`, preferring sheet names that include `Learner` or `Grade`), and filters to rows where `ULN` is a 10-digit integer and `Name` is non-empty. Output shape:

```json
{
  "sheet": "Learners & Grades",
  "headers": ["Name", "ULN", ..., "Moderation Comments"],
  "raw_headers": ["Name", "ULN", ..., "Moderation Comments"],
  "rows": [ {"_row": 2, "Name": "...", "ULN": "...", ...}, ... ]
}
```

- Record the `sheet` name — you'll pass it to `xlsx_io.py set` and to Agent 4.
- `headers` are whitespace-trimmed; `raw_headers` preserves the original cells (useful if you ever need to surface the underlying header verbatim, e.g. when explaining why a column has trailing whitespace).
- The rows skip the stats block and any non-learner rows; you can treat every entry as a real learner.

Determine whether the module has Part B by checking the column list (a `Part B` column present *and* the catalogue defining an MCB).

## Step 3 — Sample across rubric bands

Bucket learners by `Total Calculation` using the rubric bands (`scripts/rubric.py band <module> <total>` returns the band for a percentage):
- **Outstanding**: >85
- **Excellent**: 70–85
- **Very Good**: 60–69
- **Good**: 50–59
- **Satisfactory**: 40–49
- **Insufficient**: 32–39
- **Fail**: 0–31 (or non-numeric like `Refer`, `Fail`, `R`)

Skip rows where `Status` clearly indicates the learner shouldn't be moderated (withdrawn, deferred). Also skip rows whose `Total Calculation` is 0 or null when `Comments` mentions an EC / extension — surface these separately as "awaiting submission" rather than as Fail. Surface the skipped lists to the user.

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

For each confirmed learner, with row index `R` and ULN `U`:

1. **Locate the learner folder.** Look under `modules/<module>/cohorts/<cohort>/` for a folder matching either convention:
   - **Primary — by ULN prefix:** folder name starts with `<U> - ` (10-digit ULN, space-hyphen-space) or is literally just `<U>`.
   - **Fallback — by name:** strip a leading `<digits> - ` from each folder name, then compare the remainder against the row's `Name` case-insensitively with whitespace collapsed.

   If missing or empty, note it and skip — do not run any agents.

2. **Compute the tutor's band** from `Total Calculation`:
   ```
   python3 scripts/rubric.py band <module> <total>
   ```

3. **Launch Agent 1 and Agent 3 in parallel** (one message, two `Agent` tool calls):

   - `subagent_type: "independent-assessor"`, prompt containing:
     - Module code `<module>`
     - Learner folder path (the resolved folder from step 1, quoted)
     - Brief path (the resolved brief, quoted)
     - Rubric path `rubrics/L<level>.json`
     - The module catalogue JSON (from `scripts/programme.py module <module>`)
     - **Explicitly do not** include the tutor's `Total Calculation`, `Comments`, or any pre-existing `Moderation Comments`.

   - `subagent_type: "feedback-auditor"`, prompt containing:
     - Module code `<module>`
     - The tutor's `Comments` text verbatim
     - Brief path (quoted)
     - Rubric path
     - The module catalogue JSON
     - **Explicitly do not** include the learner folder path or the AI assessment.

4. **Launch Agent 2** once Agent 1 returns. `subagent_type: "assessment-comparator"`, prompt containing:
   - The full Agent 1 JSON output
   - Tutor `Total Calculation` (numeric)
   - Tutor band (from Step 4.2)
   - Tutor `Comments` text

5. **Launch Agent 4** once both Agent 2 and Agent 3 have returned. `subagent_type: "moderation-writer"`, prompt containing:
   - `xlsx_path`: the resolved grades xlsx path (quoted)
   - `sheet`: the working sheet name (from Step 2)
   - `row`: `R`
   - `module_code`: `<module>`
   - `learner_first_name`: the learner's first name (used naturally in the narrative, or omitted; never anyone else's name)
   - The Agent 2 JSON output (comparator) — used to inform substance, **not** to be quoted in the comment
   - The Agent 3 JSON output (feedback auditor) — informs paragraph 2 of the comment
   - From Agent 1: just the `strengths`, `improvements`, `general_feedback`, and `human_review_flags` arrays (NOT the full criterion ratings — Agent 2 already distilled those)

   Agent 4 writes a two-paragraph descriptive moderator comment in the Corndel house style (see `.claude/agents/moderation-writer.md`): paragraph 1 characterises the work and notes any items warranting reviewer attention; paragraph 2 comments on the tutor's feedback evidence base and MLO accuracy. **The comment must not include AI-vs-tutor language, verdict words (`endorse` / `escalate`), band names, or AI percentages.** Agent 4 writes to `Moderation sample?` and `Moderation Comments` via `xlsx_io.py set`, which (a) matches column headers whitespace-tolerantly and (b) accepts `@<path>` values to read the cell content from a UTF-8 file — use the file path syntax for the multi-paragraph comment so newlines survive shell quoting.

6. **Retain** Agent 1's full JSON and Agent 2's verdict in your working notes — you'll need them for Step 5 (overall summary) and Step 6 (DB payload).

7. **Optional persistence.** Save Agent 1's full output to `<learner_folder>/ai_assessment.json` (the folder is gitignored, so this stays local). Provides a paper trail if the moderation is later audited.

If any agent fails or returns malformed JSON, surface the error to the user, skip the xlsx write for that learner, and continue with the next.

## Step 5 — Overall module moderation summary

After all sampled learners are processed, write an overall summary into the xlsx in the **same Corndel descriptive house style** as the per-learner comments — no verdict counts, no AI-vs-tutor delta language, no escalation tallies.

**Sheet selection.** Look at the workbook's sheet names (from `xlsx_io.py columns`) and pick in this order:
1. A sheet named `Moderation Summary` — write into it as appropriate.
2. A sheet named `Moderation Report` — the Corndel template. It has a pre-laid form in column A (`Moderated by`, `Date`, `Sample Size`, `Standard Deviation`, `Grade distribution comments`, `General Comments`, `Validity of grades`) with values expected in column B. Populate each row's column B; use `xlsx_io.py set` with the row index and column `B`. Multi-paragraph cells (General Comments, Validity of grades) should be written via the `@<path>` value syntax for newline safety.
3. Neither present — ask the user where the summary should go (new sheet, dedicated cell, or appended row) before writing.

**Content.** Write three substantive cells (or a single combined paragraph if the user prefers a free-form layout):

- **Grade distribution comments**: factual description of the cohort centroid (mean / median / mode / range / std dev) and the band distribution. Anonymised — refer to bands, not learners.
- **General Comments**: 2–3 short paragraphs describing what is consistently strong across the sample (specific dimensions like Practical Realisation, ethical reasoning, quantified outcomes), what would benefit from more support (specific gaps like source breadth, written register, statistical rigour, brief compliance), and one short paragraph on tutor feedback patterns observed across the sample. Use the same descriptive vocabulary as the per-learner comments — no verdict counts, no escalation language, no AI-vs-tutor framing.
- **Validity of grades**: 1–2 paragraphs noting which awards are well-evidenced and which have items warranting reviewer attention before sign-off (broken artefact links, brief-compliance breaches, missing references, format violations, EC-awaiting cases). Frame items as observations requiring confirmation, not as escalations.

Keep the summary anonymised throughout — refer to learners by band, count, or position in the distribution; never by name.

## Step 6 — Update the analytics DB

This step is mandatory and runs after the xlsx is updated.

1. Verify the analytics DB is initialised. If `analytics.db` or `.env` is missing, tell the user to run `python3 scripts/db.py init` and stop.

2. Build a JSON payload covering **every** learner in the cohort (not just sampled ones — full cohort gives proper band distributions). For sampled learners, include the AI percentage / band / comparator verdict drawn from Agents 1 and 2. Shape:
   ```json
   {
     "module_code": "<module>",
     "cohort_code": "<cohort>",
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

3. Pipe the payload to the DB script. Write it to a file inside the (gitignored) cohort folder and redirect — that's more robust than `echo` for nested JSON and works cross-platform:
   ```
   python3 scripts/db.py record-pass < "modules/<module>/cohorts/<cohort>/.payload.json"
   ```

4. Report the `pass_id` returned by the script.

## Step 7 — Generate the cohort moderation report

Runs after the DB has been updated. Produces an anonymised markdown report at `modules/<module>/moderation_<cohort>.md` plus PNG charts under `modules/<module>/charts/`. Both paths sit outside the gitignored `cohorts/` tree, so the report is shareable and version-controllable.

If `<cohort>` contains spaces, the report path contains spaces too — make sure every path use is quoted.

1. **Aggregate qualitative material** across the sampled learners' Agent 1 outputs. Synthesise (don't just list):

   - **3–5 cohort-level strengths** — recurring strengths across multiple learners. Each must be specific and rubric-anchored (cite a criterion). Phrase in third-person about the cohort, not about individuals. Anonymise.
   - **3–5 cohort-level points for improvement** — recurring weaknesses or under-evidenced criteria. Same rubric-anchoring and anonymisation rules.
   - **2–3 recommendations** — actions for the module team. Draw from comparator escalations, auditor issues, and patterns in the AI's improvement lists.

2. **Build the injection JSON:**
   ```json
   {
     "strengths":       ["...", "...", "..."],
     "improvements":    ["...", "...", "..."],
     "recommendations": ["...", "..."]
   }
   ```

3. **Run the report generator**, piping the JSON via stdin (file path inside the gitignored cohort folder):
   ```
   python3 scripts/report.py generate "<module>" "<cohort>" < "modules/<module>/cohorts/<cohort>/.inject.json"
   ```
   The script reads the grades xlsx, the latest analytics-DB pass for this module/cohort, the programme catalogue and the level rubric. It computes overall stats (mean, median, std dev, range), the band distribution, per-assessor stats (anonymised as Assessor A/B/C), AI/tutor agreement (mean delta, verdict counts), and themes-by-LO. It renders charts via matplotlib where available; if matplotlib is missing, the report still generates without charts.

4. **Verify the report.** Read the resulting `modules/<module>/moderation_<cohort>.md` and skim it for:
   - No learner names anywhere (the script anonymises, but double-check the qualitative sections you wrote).
   - Sample size and band distribution match what you actually moderated.
   - Charts referenced in the report actually exist under `modules/<module>/charts/`.

   If matplotlib was missing, surface that fact to the user with the install hint.

## Step 8 — Final report to the user

Tell the user:
- Which learners were sampled and from which bands
- A one-line moderation outcome per sampled learner
- Where the overall summary lives in the xlsx
- The analytics `pass_id` and how many learners + themes were recorded
- The path to the generated cohort report (`modules/<module>/moderation_<cohort>.md`) and whether charts were generated
- Anything that needs follow-up

Remind the user that `analytics.db`, `modules/<module>/moderation_<cohort>.md`, and any new files under `modules/<module>/charts/` have changed locally — to share with collaborators they should:
```
git add analytics.db "modules/<module>/moderation_<cohort>.md" "modules/<module>/charts/"
git commit -m "Moderation pass: <module> <cohort>"
git push
```
Do not run those commands yourself. The grades xlsx and learner folders are gitignored and stay local.
