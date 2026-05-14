---
description: Report on anonymised moderation analytics for a module (optionally scoped to a cohort)
argument-hint: <module> [<cohort>] [free-form question]
---

You are reporting analytics from the moderation tool's anonymised SQLite database.

The user invoked: `/analytics $ARGUMENTS`

Parse `$ARGUMENTS`:
- `$1` = module code (e.g. `DT604`) — **required**
- `$2` = cohort code (e.g. `Sep23`) — optional
- Anything after the recognised positional args is a free-form natural-language question.

If `$1` is missing, tell the user the expected form and stop.

## Prerequisites

- `analytics.db` must exist at the repo root.
- `.env` must contain `MODERATION_HASH_SALT`.

If either is missing, tell the user to run `python3 scripts/db.py init` and stop.

## Step 1 — Pre-canned summary

Always start by fetching the standard summary:

```
python3 scripts/db.py summary $1 [$2]
```

The script returns JSON with:
- `overall`: count of learners recorded, mean total, min/max, sampled count
- `bands`: band distribution
- `top_themes`: most frequent moderator themes (with their cumulative counts)
- `themes_by_lo`: counts of LO-tagged themes grouped by learning outcome
- `recent_passes`: up to 20 most recent moderation passes in scope

Cross-reference the LO IDs against the programme catalogue so the user sees outcome descriptions, not just IDs:
```
python3 scripts/programme.py los $1
```
For each `lo_id` returned in `themes_by_lo`, find the matching description and (optionally) roll up to programme-level learning outcomes via the `programmeLearningOutcomes` field on each LO.

Render this for the user as a compact, readable report:

- Headline line: "`DT604 — Project Report` / Sep23 — 18 learners moderated across 1 pass."
- Band distribution as a simple table or list.
- Mean / min / max total.
- Top 5–10 themes with counts.
- **LO breakdown**: each LO with its description and the cumulative count of themes touching it. Call out any LO with disproportionately high theme volume (likely cohort weakness) or with zero themes after multiple passes (potentially under-assessed).
- **Programme-level rollup** (optional, only when several passes exist): aggregate LO theme counts by their `programmeLearningOutcomes` mapping.
- Recent passes with `run_at` and `sample_size`.

## Step 2 — Free-form follow-up

If the user supplied a free-form question after the positional args (or asks one as a follow-up message), translate it to a single `SELECT` query and run:

```
python3 scripts/db.py query --sql "<SELECT ...>"
```

Schema you can query against:

```
moderation_passes(id, module_code, cohort_code, run_at, sample_size, overall_summary)
learner_grades(pass_id, learner_key, module_code, cohort_code,
               part_a, part_b, total, band, was_sampled)
moderator_themes(pass_id, module_code, cohort_code, theme, count, notes, lo_id)
```

Constraints:
- Only `SELECT` is permitted. The script rejects anything else.
- `learner_key` is a salted SHA-256 hash — do not try to reverse it.
- For cross-cohort comparisons, group by `cohort_code`. For cross-module, group by `module_code`.
- When a query returns more than ~20 rows, summarise rather than dumping all rows.

Examples of questions to expect:
- "How does Sep23 compare to Jan23 on DT604?" → group by cohort, compare means and band distributions.
- "Which themes show up across every cohort?" → group by theme, count distinct cohort_codes.
- "Which LO is the weakest cohort-wide on DT604?" → group by `lo_id`, sum `count`, cross-reference description from `programme.py los DT604`.
- "Are there learners (anonymised) showing up in multiple modules with declining totals?" → join on `learner_key` across modules, look for negative deltas.

## Output

- Don't dump raw JSON to the user. Always render a short, readable report.
- Surface the SQL you ran for transparency, e.g. "Query: `SELECT ...`".
- If the data is sparse (e.g. only one pass exists), say so — don't invent trends.

Do not modify the database. Only read.
