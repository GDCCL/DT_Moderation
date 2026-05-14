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

- Brief:   `modules/$1/brief.*`   (one of `.pdf`, `.docx`, `.md`, `.txt`)
- Rubric:  `modules/$1/rubric.*`
- Cohort:  `modules/$1/cohorts/$2/`
- Grades:  `modules/$1/cohorts/$2/grades.xlsx`

Stop and tell the user if any are missing.

## Grades xlsx schema (fixed)

Columns: `Name`, `ULN`, `PDE`, `Client`, `Status`, `Cohort`, `Part A`, `Part B` (optional — Part A-only modules omit it), `Total Calculation`, `Assessed By`, `Comments`, `Moderation sample?`, `Moderation Comments`.

- `Comments` is the **tutor's assessment feedback** — read it, don't overwrite.
- `Moderation sample?` is where you set `Y` on every sampled learner.
- `Moderation Comments` is where the moderator comment goes.
- `Total Calculation` is the figure to band on.

## Step 1 — Load module context

Read the brief and rubric. Keep both in working memory.

- `.pdf`, `.md`, `.txt`: use the Read tool directly.
- `.docx`: convert via `pandoc <file> -t plain` or `python3 -c "from docx import Document; print('\n'.join(p.text for p in Document('<file>').paragraphs))"`.

If neither works, tell the user how to install one and stop.

## Step 2 — Read the grades xlsx

```
python3 scripts/xlsx_io.py columns modules/$1/cohorts/$2/grades.xlsx
python3 scripts/xlsx_io.py rows    modules/$1/cohorts/$2/grades.xlsx <sheet>
```

Determine whether the module has Part B by checking the column list. Note which sheet name is in use.

## Step 3 — Sample across grade boundaries

Bucket learners by `Total Calculation`:
- **Distinction**: 70+
- **Merit**: 60–69
- **Pass (upper)**: 50–59
- **Pass (lower)**: 40–49
- **Refer / Fail**: < 40 or non-numeric (`Refer`, `Fail`, `R`)

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

4. Assess the work against the brief and rubric. Decide whether the awarded `Total Calculation` is defensible against rubric criteria. Cite specific criteria.

5. Write to the xlsx:
   ```
   python3 scripts/xlsx_io.py set modules/$1/cohorts/$2/grades.xlsx <sheet> <row> "Moderation sample?" "Y"
   python3 scripts/xlsx_io.py set modules/$1/cohorts/$2/grades.xlsx <sheet> <row> "Moderation Comments" "<comment>"
   ```
   The comment must:
   - State whether you agree with the awarded band, with one-line rationale.
   - Cite at least one rubric criterion that supports the call.
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
        "notes": "<one-line explanation, anonymised>"}
     ]
   }
   ```

   - Omit `part_b` for Part A-only modules.
   - Skip learners with no ULN (warn the user).
   - Themes are short labels you extract from your moderator comments — e.g. `criterion-3-strong`, `evidence-thin-on-criterion-1`, `tutor-under-marking-distinctions`. Aim for 3–8 themes total, with `count` reflecting how many sampled learners showed each.

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
