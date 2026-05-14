# DT_Moderation

A Claude Code slash-command toolkit for assessing and moderating degree-apprenticeship work on the DTSP (BSc Digital Technology Solutions Professional) programme. Slash commands, subagent definitions, the programme catalogue and the level rubrics live in this repo and are shared across every chat that clones it; learner submissions and grades stay local for GDPR.

## Quickstart

1. **Install dependencies** (one-time per machine):
   ```bash
   pip install openpyxl matplotlib python-docx
   ```
   `matplotlib` enables charts in the cohort report (optional — without it the report still generates, minus charts). `python-docx` is only needed if your briefs or learner work include `.docx` files; `pandoc` works as an alternative.

2. **Initialise the analytics DB and hash salt** (one-time per repo):
   ```bash
   python3 scripts/db.py init
   ```
   This creates `analytics.db` and a fresh `.env` with a salted-SHA-256 key. **Share the salt with collaborators out of band** (password manager, etc.) — do not commit `.env`. Collaborators on a clean clone should paste the same salt into their own `.env` rather than running `init` again.

3. **Set up a module** (one-time per module):
   ```bash
   mkdir modules/DT604
   # drop brief.pdf (or .docx / .md / .txt) into modules/DT604/
   ```
   The level rubric is already in `rubrics/L<n>.json` and the programme catalogue is in `modules/programme.json` — both shared.

4. **Set up a cohort** (per cohort, locally — gitignored):
   ```bash
   mkdir -p modules/DT604/cohorts/Sep23
   # drop grades.xlsx into modules/DT604/cohorts/Sep23/
   # drop each learner's work into modules/DT604/cohorts/Sep23/<Learner Name>/
   ```

5. **Run the tool from a Claude Code chat:**
   ```text
   /setup-cohort DT604 Sep23   # pre-flight check, no writes
   /moderate    DT604 Sep23   # runs the four-agent pipeline, writes xlsx, DB, and report
   /analytics   DT604 Sep23   # query module/cohort analytics
   ```

6. **Share the new pass** (after each `/moderate`):
   ```bash
   git add analytics.db modules/DT604/moderation_Sep23.md modules/DT604/charts/
   git commit -m "Moderation pass: DT604 Sep23"
   git push
   ```

## Slash commands

- **`/setup-cohort <module> <cohort>`** — read-only pre-flight. Verifies the module code is in the catalogue, brief and level rubric exist, grades xlsx columns match the expected schema (`Name`, `ULN`, `PDE`, `Client`, `Status`, `Cohort`, `Part A`, `Part B`, `Total Calculation`, `Assessed By`, `Comments`, `Moderation sample?`, `Moderation Comments`), and every xlsx name has a matching learner folder. Flags near-miss typos, empty folders, and missing ULNs.

- **`/moderate <module> <cohort>`** — samples ≥6 learners spanning the populated rubric bands (`Fail` → `Outstanding`), runs the four-agent pipeline per sampled learner, writes moderator comments + `Y` flags into `Moderation Comments` / `Moderation sample?`, records every learner's grades (full cohort) and the AI percentages, verdicts and themes to `analytics.db`, and generates the cohort report at `modules/<MOD>/moderation_<COHORT>.md`.

- **`/analytics <module> [<cohort>] [question]`** — renders the standard summary (band distribution, top themes, themes-by-LO, AI/tutor agreement) and accepts free-form follow-up questions that translate to read-only `SELECT` queries against the DB.

## The four-agent pipeline

Each sampled learner is moderated by four subagents (defined in `.claude/agents/`) with strict information firewalls so the AI never grades its own homework:

| Agent | Inputs | Forbidden inputs |
|---|---|---|
| `independent-assessor` | brief, rubric, learner work | tutor grade, tutor `Comments` |
| `feedback-auditor` | brief, rubric, tutor `Comments` | learner work, AI assessment |
| `assessment-comparator` | Agent 1's JSON output, tutor grade + `Comments` | learner work directly |
| `moderation-writer` | Agents 2 & 3 outputs, AI strengths/improvements | the work, the tutor feedback directly |

Agents 1 and 3 run in parallel, Agent 2 waits on 1, Agent 4 waits on 2 and 3. The orchestrator (`/moderate`) holds the full picture from the xlsx but hands each subagent only its allowed slice.

## File layout

```
DT_Moderation/
├── .claude/
│   ├── agents/                       # subagent definitions
│   │   ├── independent-assessor.md
│   │   ├── feedback-auditor.md
│   │   ├── assessment-comparator.md
│   │   └── moderation-writer.md
│   └── commands/                     # slash-command definitions
│       ├── setup-cohort.md
│       ├── moderate.md
│       └── analytics.md
├── modules/
│   ├── programme.json                # DTSP catalogue (12 modules, LOs, challenges)
│   └── <MOD>/                        # one folder per module (e.g. DT604/)
│       ├── brief.{pdf|docx|md|txt}
│       ├── moderation_<COHORT>.md    # generated cohort report (tracked, anonymised)
│       ├── charts/                   # generated PNG charts (tracked, anonymised)
│       └── cohorts/                  # ─── gitignored ───
│           └── <COHORT>/
│               ├── grades.xlsx
│               └── <Learner Name>/
│                   ├── <submission files>
│                   └── ai_assessment.json   # Agent 1's full output (audit trail)
├── rubrics/
│   ├── L4.json                       # DT4xx
│   ├── L5.json                       # DT5xx
│   └── L6.json                       # DT6xx
├── scripts/
│   ├── xlsx_io.py                    # read/write xlsx cells
│   ├── programme.py                  # module/LO/challenge lookups
│   ├── rubric.py                     # rubric + level + band lookups
│   ├── db.py                         # analytics SQLite + salted ULN hashing
│   └── report.py                     # cohort moderation report generator
├── analytics.db                      # anonymised cohort analytics (tracked)
├── .env                              # MODERATION_HASH_SALT (gitignored)
├── .env.example
└── .gitignore
```

## Data handling

- **Gitignored** (stays on each operator's machine): everything under `modules/*/cohorts/` (submissions, grades xlsx, per-learner AI assessment dumps) and `.env` (the hash salt).
- **Tracked** (shareable via git): slash commands, subagent definitions, programme catalogue, level rubrics, helper scripts, `analytics.db` (only salted hashes — no ULNs or names), generated cohort reports + charts (anonymised — assessors labelled `Assessor A/B/C`, no learner names).
- **Hashed ULNs** let the same learner be tracked across modules and cohorts for trend analysis without exposing identity. Collaborators must share the same salt for hashes to align.

## Grade bands (rubric-aligned)

| Band | Range |
|---|---|
| Fail | 0–31% |
| Insufficient | 32–39% |
| Satisfactory | 40–49% |
| Good | 50–59% |
| Very Good | 60–69% |
| Excellent | 70–85% |
| Outstanding | >85% |

Module → level mapping is the second digit of the code: `DT4xx` → L4, `DT5xx` → L5, `DT6xx` → L6.

## Conventions

- The 10 rubric criteria (`Critical Thinking`, `Creative Problem Solving`, …, `Communication`) map 1-to-1 to the programme-level outcomes in `programme.json`. Per-module learning outcomes (`LO1`–`LO4`) reference subsets of these criteria via their `programmeLearningOutcomes` field, which is how the analytics DB's `lo_id` tags roll up to rubric criteria.
- Moderator comments target 80–150 words, cite at least one rubric criterion + band, reference at least one module LO ID, and contain no names other than the learner's first name.
- The cohort report is regenerated on every `/moderate` run; commit it deliberately when you want to share that pass.
