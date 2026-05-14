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

## Step 4 — Moderate each sampled learner

For each confirmed learner, in order:

1. Locate `modules/$1/cohorts/$2/<Learner Name>/`. If the folder is missing or empty, note this and skip — do not invent content.

2. Walk the folder. Handle by file type:
   - `.pdf`, `.md`, `.txt`, source code: read directly.
   - `.docx`: convert as in Step 1.
   - `.xlsx`: dump via `scripts/xlsx_io.py`.
   - `.mp4`, `.mov`, `.wav`, `.mp3`: **do not attempt to read.** Add the file to this learner's "needs human review" list and call it out in the moderator comment.
   - Git repos / nested project folders: read the README first, then sample top-level source files. Don't try to read every file.

3. Read the `Comments` column for this learner from the xlsx — that's the tutor's feedback. Use it as context but form your own view independently.

4. Assess the work against the brief and the **level rubric loaded in Step 1**. For each of the 10 criteria where the submission produces enough evidence to judge, identify which band the work falls into and quote (or closely paraphrase) the relevant descriptor. Decide whether the awarded `Total Calculation` is defensible: the awarded band should match the modal band across the criteria that the module's LOs actually exercise.

5. Write to the xlsx:
   ```
   python3 scripts/xlsx_io.py set modules/$1/cohorts/$2/grades.xlsx <sheet> <row> "Moderation sample?" "Y"
   python3 scripts/xlsx_io.py set modules/$1/cohorts/$2/grades.xlsx <sheet> <row> "Moderation Comments" "<comment>"
   ```
   The comment must:
   - State whether you agree with the awarded band, with one-line rationale.
   - Cite at least one **rubric criterion** with the band you'd place the work in, naming both (e.g. "Critical Thinking — Very Good: arguments coherently expressed and well-supported"). The cited band's descriptor must come from the level rubric loaded in Step 1.
   - Tie that criterion back to the relevant **learning outcome ID** for this module via the LO → criterion map you built in Step 1.4 (e.g. "evidences LO2 strongly").
   - Reference module challenges by ID (`MCA`, `MCB`) when commenting on weighting/coverage.
   - Flag any video/audio artefacts that need human review.
   - Stay concise — target 80–150 words.
   - Contain **no names** other than the learner's first name once (or none). Do not mention other learners, the tutor's name, or employer specifics.

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

2. Build a JSON payload covering **every** learner in the cohort (not just sampled ones — full cohort gives proper band distributions). Shape:
   ```json
   {
     "module_code": "$1",
     "cohort_code": "$2",
     "overall_summary": "<the Step 5 summary, anonymised>",
     "learners": [
       {"uln": "<ULN as string>", "part_a": 65, "part_b": 70,
        "total": 67.5, "band": "Merit", "was_sampled": true}
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
   - Themes are short labels keyed to rubric criteria, e.g. `critical-thinking-strong`, `digital-proficiency-thin`, `professionalism-evidenced-via-collaboration`, or cross-cutting patterns like `tutor-under-marking-very-good-band`. Aim for 3–8 themes total, with `count` reflecting how many sampled learners showed each.
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
