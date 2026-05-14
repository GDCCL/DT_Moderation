#!/usr/bin/env python3
"""Generate an anonymised cohort moderation report.

Reads grades xlsx + analytics.db + programme catalogue + level rubric.
Writes markdown to `modules/<MOD>/moderation_<COHORT>.md` and PNG charts to
`modules/<MOD>/charts/<COHORT>_*.png`. Both are tracked in git, so all
content is anonymised — no learner names, assessors labelled A/B/C.

Usage:
  report.py generate <module> <cohort> [--no-charts]

Optionally pass an injection JSON via stdin to populate qualitative sections:
  {
    "strengths":       ["...", "...", "..."],
    "improvements":    ["...", "...", "..."],
    "recommendations": ["...", "..."]
  }
"""
import json
import re
import sqlite3
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "analytics.db"
PROGRAMME = ROOT / "modules" / "programme.json"

BAND_ORDER = ["Fail", "Insufficient", "Satisfactory", "Good", "Very Good", "Excellent", "Outstanding"]
BAND_RANGES = {
    "Fail": (0, 31.999),
    "Insufficient": (32, 39.999),
    "Satisfactory": (40, 49.999),
    "Good": (50, 59.999),
    "Very Good": (60, 69.999),
    "Excellent": (70, 85.0),
    "Outstanding": (85.001, 100),
}


def band_for(total):
    if not isinstance(total, (int, float)):
        return "Fail"
    for name, (lo, hi) in BAND_RANGES.items():
        if lo <= total <= hi:
            return name
    return "Fail"


def level_for(code):
    m = re.match(r"^DT([4-6])\d\d$", code.upper())
    return f"L{m.group(1)}" if m else None


def load_programme():
    return json.loads(PROGRAMME.read_text())


def find_module(programme, code):
    for m in programme["modules"]:
        if m["code"].upper() == code.upper():
            return m
    sys.exit(f"Module {code} not in programme catalogue.")


def read_xlsx_rows(path):
    try:
        from openpyxl import load_workbook
    except ImportError:
        sys.exit("openpyxl required. Run: pip install openpyxl")
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in row):
            continue
        rec = {}
        for h, v in zip(headers, row):
            rec[h] = v
        rows.append(rec)
    return rows


def latest_pass(conn, module, cohort):
    row = conn.execute(
        "SELECT id FROM moderation_passes WHERE module_code = ? AND cohort_code = ? "
        "ORDER BY run_at DESC LIMIT 1",
        (module, cohort),
    ).fetchone()
    return row[0] if row else None


def anonymise_assessors(rows):
    """Map 'Assessed By' values to Assessor A/B/C in order of first appearance."""
    mapping = {}
    next_letter = ord("A")
    for r in rows:
        name = (r.get("Assessed By") or "").strip()
        if not name:
            continue
        if name not in mapping:
            mapping[name] = f"Assessor {chr(next_letter)}"
            next_letter += 1
    return mapping


def safe_stdev(values):
    return round(statistics.stdev(values), 2) if len(values) >= 2 else 0.0


def stats_for(values):
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return {"n": 0}
    return {
        "n": len(nums),
        "mean": round(statistics.mean(nums), 2),
        "median": round(statistics.median(nums), 2),
        "stdev": safe_stdev(nums),
        "min": round(min(nums), 2),
        "max": round(max(nums), 2),
    }


def make_charts(module, cohort, rows, db_rows, assessor_map, themes_by_lo, charts_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    charts_dir.mkdir(parents=True, exist_ok=True)
    totals = [r["Total Calculation"] for r in rows if isinstance(r.get("Total Calculation"), (int, float))]

    # Band distribution
    counts = {b: 0 for b in BAND_ORDER}
    for t in totals:
        counts[band_for(t)] += 1
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(BAND_ORDER, [counts[b] for b in BAND_ORDER])
    ax.set_title(f"{module} {cohort} — grade band distribution")
    ax.set_ylabel("learners")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    fig.savefig(charts_dir / f"{cohort}_band_distribution.png", dpi=110)
    plt.close(fig)

    # Per-assessor box plot
    by_assessor = {}
    for r in rows:
        name = (r.get("Assessed By") or "").strip()
        total = r.get("Total Calculation")
        if name and isinstance(total, (int, float)):
            by_assessor.setdefault(assessor_map.get(name, name), []).append(total)
    if len(by_assessor) >= 2:
        fig, ax = plt.subplots(figsize=(7, 4))
        labels = sorted(by_assessor.keys())
        ax.boxplot([by_assessor[k] for k in labels], labels=labels)
        ax.set_title(f"{module} {cohort} — grade by assessor (anonymised)")
        ax.set_ylabel("total %")
        plt.tight_layout()
        fig.savefig(charts_dir / f"{cohort}_per_assessor.png", dpi=110)
        plt.close(fig)

    # AI vs Tutor scatter
    paired = [(r["ai_percentage"], r["total"]) for r in db_rows
              if r.get("ai_percentage") is not None and r.get("total") is not None]
    if paired:
        fig, ax = plt.subplots(figsize=(6, 6))
        xs, ys = zip(*paired)
        ax.scatter(xs, ys)
        lo, hi = min(min(xs), min(ys)) - 5, max(max(xs), max(ys)) + 5
        ax.plot([lo, hi], [lo, hi], linestyle="--", linewidth=1)
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_xlabel("Independent AI assessment (%)")
        ax.set_ylabel("Tutor awarded (%)")
        ax.set_title(f"{module} {cohort} — AI vs tutor (sampled)")
        plt.tight_layout()
        fig.savefig(charts_dir / f"{cohort}_ai_vs_tutor.png", dpi=110)
        plt.close(fig)

    # Themes by LO
    if themes_by_lo:
        fig, ax = plt.subplots(figsize=(7, 4))
        lo_ids = list(themes_by_lo.keys())
        counts = [themes_by_lo[k] for k in lo_ids]
        ax.barh(lo_ids, counts)
        ax.set_xlabel("theme volume")
        ax.set_title(f"{module} {cohort} — themes by learning outcome")
        plt.tight_layout()
        fig.savefig(charts_dir / f"{cohort}_themes_by_lo.png", dpi=110)
        plt.close(fig)

    return True


def render_markdown(ctx):
    lines = []
    a = lines.append
    m = ctx["module_meta"]
    a(f"# {m['code']} — {m['title']}")
    a(f"## Moderation Report — {ctx['cohort']} cohort")
    a("")
    a(f"*Generated: {ctx['generated_at']} · Level: {ctx['level']}*")
    a("")
    a("> This report is anonymised. Learner names are omitted; assessors are labelled "
      "Assessor A / B / C in order of first appearance in the cohort spreadsheet.")
    a("")

    # 1. Overview
    a("## 1. Overview")
    a("")
    a(f"- **Module:** {m['code']} — {m['title']} ({ctx['level']})")
    a(f"- **Cohort:** {ctx['cohort']}")
    a(f"- **Total cohort:** {ctx['n_total']} learners")
    a(f"- **Sampled for moderation:** {ctx['n_sampled']}")
    if ctx["assessor_map"]:
        a(f"- **Assessors:** {len(ctx['assessor_map'])} ({', '.join(sorted(set(ctx['assessor_map'].values())))})")
    a("")

    # 2. Grade distribution
    a("## 2. Grade distribution")
    a("")
    s = ctx["overall_stats"]
    if s.get("n"):
        a(f"Mean **{s['mean']}%** · Median **{s['median']}%** · Std dev **{s['stdev']}** · "
          f"Range **{s['min']}–{s['max']}%**")
    a("")
    if ctx["chart_band"]:
        a(f"![Band distribution](charts/{ctx['cohort']}_band_distribution.png)")
        a("")
    a("| Band | Count | % of cohort |")
    a("|---|---|---|")
    total_n = max(s.get("n", 0), 1)
    for b in reversed(BAND_ORDER):
        c = ctx["band_counts"].get(b, 0)
        pct = round(100 * c / total_n, 1) if c else 0
        a(f"| {b} | {c} | {pct}% |")
    a("")

    # 3. Inter-assessor consistency
    a("## 3. Inter-assessor consistency")
    a("")
    if len(ctx["assessor_stats"]) < 2:
        a("Single assessor on this cohort — no inter-assessor comparison.")
    else:
        a("| Assessor | Marked | Mean | Median | Std dev | Min | Max |")
        a("|---|---|---|---|---|---|---|")
        for label, st in sorted(ctx["assessor_stats"].items()):
            a(f"| {label} | {st['n']} | {st['mean']} | {st['median']} | {st['stdev']} | {st['min']} | {st['max']} |")
        means = [st["mean"] for st in ctx["assessor_stats"].values()]
        spread = round(max(means) - min(means), 2)
        a("")
        a(f"Mean grade differs by **{spread} percentage points** across assessors.")
        a("")
        if ctx["chart_assessor"]:
            a(f"![Per-assessor distribution](charts/{ctx['cohort']}_per_assessor.png)")
    a("")

    # 4. AI / tutor agreement
    a("## 4. AI / tutor agreement")
    a("")
    if not ctx["ai_pairs"]:
        a("No AI assessments recorded for this cohort yet.")
    else:
        a("| Verdict | Count |")
        a("|---|---|")
        for verdict, n in ctx["verdict_counts"].items():
            a(f"| {verdict} | {n} |")
        a("")
        delta = ctx["mean_delta"]
        direction = "higher" if delta > 0 else "lower"
        a(f"Tutors mark on average **{abs(round(delta, 2))} pp {direction}** than the independent AI assessor on sampled learners.")
        a("")
        if ctx["chart_ai"]:
            a(f"![AI vs tutor](charts/{ctx['cohort']}_ai_vs_tutor.png)")
    a("")

    # 5. Strengths
    a("## 5. Strengths")
    a("")
    if ctx["inject"].get("strengths"):
        for s in ctx["inject"]["strengths"]:
            a(f"- {s}")
    else:
        a("_No qualitative strengths supplied._")
    a("")

    # 6. Improvements
    a("## 6. Points for improvement")
    a("")
    if ctx["inject"].get("improvements"):
        for s in ctx["inject"]["improvements"]:
            a(f"- {s}")
    else:
        a("_No qualitative improvements supplied._")
    a("")

    # 7. Themes by LO
    a("## 7. Themes by learning outcome")
    a("")
    if ctx["themes_table"]:
        a("| LO | Description | Theme volume |")
        a("|---|---|---|")
        for lo_id, desc, count in ctx["themes_table"]:
            a(f"| {lo_id} | {desc} | {count} |")
        a("")
        if ctx["chart_themes"]:
            a(f"![Themes by LO](charts/{ctx['cohort']}_themes_by_lo.png)")
    else:
        a("_No LO-tagged themes recorded for this cohort yet._")
    a("")

    # 8. Recommendations
    a("## 8. Recommendations")
    a("")
    if ctx["inject"].get("recommendations"):
        for r in ctx["inject"]["recommendations"]:
            a(f"- {r}")
    else:
        a("_No recommendations supplied._")
    a("")

    # 9. Methodology
    a("## 9. Methodology")
    a("")
    a("Moderation followed a four-agent pipeline per sampled learner with strict information firewalls:")
    a("")
    a("1. **Independent AI assessor** — read only the brief, level rubric and learner work; never saw the tutor's grade or feedback.")
    a("2. **Feedback auditor** — read only the brief, level rubric and tutor's written feedback; never saw the learner work.")
    a("3. **Assessment comparator** — compared the AI assessment against the tutor's grade and feedback; emitted a verdict (endorse / endorse-with-note / escalate).")
    a("4. **Moderation writer** — synthesised the moderator comment and recorded it against each sampled learner.")
    a("")
    a("Sampling targeted ≥6 learners spanning the populated grade bands. The full cohort (including non-sampled learners) is recorded in the anonymised analytics database for trend analysis.")
    a("")
    a("---")
    a("*Anonymised report generated by the apprenticeship moderation tool.*")
    return "\n".join(lines) + "\n"


def cmd_generate(module, cohort, no_charts=False):
    programme = load_programme()
    module_meta = find_module(programme, module)
    level = level_for(module)
    if not level:
        sys.exit(f"Module code '{module}' is not in form DT[4-6]\\d\\d.")

    module_dir = ROOT / "modules" / module
    cohort_dir = module_dir / "cohorts" / cohort
    xlsx = cohort_dir / "grades.xlsx"
    if not xlsx.exists():
        sys.exit(f"Grades xlsx not found at {xlsx}.")

    rows = read_xlsx_rows(xlsx)
    assessor_map = anonymise_assessors(rows)

    totals = [r.get("Total Calculation") for r in rows]
    overall_stats = stats_for(totals)
    band_counts = {b: 0 for b in BAND_ORDER}
    for t in totals:
        if isinstance(t, (int, float)):
            band_counts[band_for(t)] += 1

    by_assessor = {}
    for r in rows:
        name = (r.get("Assessed By") or "").strip()
        total = r.get("Total Calculation")
        if name and isinstance(total, (int, float)):
            label = assessor_map.get(name, name)
            by_assessor.setdefault(label, []).append(total)
    assessor_stats = {k: stats_for(v) for k, v in by_assessor.items()}

    # DB data — latest pass for this module/cohort
    ai_pairs = []
    verdict_counts = {}
    themes_by_lo_count = {}
    themes_table = []
    mean_delta = 0.0
    db_rows = []

    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        pass_id = latest_pass(conn, module, cohort)
        if pass_id is not None:
            grade_rows = [dict(r) for r in conn.execute(
                "SELECT * FROM learner_grades WHERE pass_id = ?", (pass_id,)
            ).fetchall()]
            db_rows = grade_rows
            for r in grade_rows:
                if r.get("ai_percentage") is not None and r.get("total") is not None:
                    ai_pairs.append((r["ai_percentage"], r["total"]))
                v = r.get("verdict")
                if v:
                    verdict_counts[v] = verdict_counts.get(v, 0) + 1
            if ai_pairs:
                deltas = [t - a for a, t in ai_pairs]
                mean_delta = statistics.mean(deltas)
            theme_rows = conn.execute(
                "SELECT lo_id, SUM(count) AS n FROM moderator_themes "
                "WHERE pass_id = ? AND lo_id IS NOT NULL GROUP BY lo_id ORDER BY n DESC",
                (pass_id,),
            ).fetchall()
            lo_desc = {lo["id"]: lo["description"] for lo in module_meta.get("learningOutcomes", [])}
            for tr in theme_rows:
                themes_by_lo_count[tr["lo_id"]] = tr["n"]
                themes_table.append((tr["lo_id"], lo_desc.get(tr["lo_id"], "—"), tr["n"]))
        conn.close()

    inject = {}
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            try:
                inject = json.loads(raw)
            except json.JSONDecodeError as e:
                sys.exit(f"Could not parse stdin JSON: {e}")

    charts_dir = module_dir / "charts"
    has_charts = False
    if not no_charts:
        has_charts = make_charts(module, cohort, rows, db_rows, assessor_map, themes_by_lo_count, charts_dir)

    ctx = {
        "module_meta": module_meta,
        "level": level,
        "cohort": cohort,
        "n_total": overall_stats.get("n", 0),
        "n_sampled": sum(1 for r in rows if str(r.get("Moderation sample?") or "").strip().upper() == "Y"),
        "assessor_map": assessor_map,
        "overall_stats": overall_stats,
        "band_counts": band_counts,
        "assessor_stats": assessor_stats,
        "ai_pairs": ai_pairs,
        "verdict_counts": verdict_counts,
        "mean_delta": mean_delta,
        "themes_table": themes_table,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "chart_band": has_charts,
        "chart_assessor": has_charts and len(assessor_stats) >= 2,
        "chart_ai": has_charts and bool(ai_pairs),
        "chart_themes": has_charts and bool(themes_by_lo_count),
        "inject": inject,
    }

    md = render_markdown(ctx)
    out_path = module_dir / f"moderation_{cohort}.md"
    out_path.write_text(md)
    print(json.dumps({
        "ok": True,
        "report": str(out_path.relative_to(ROOT)),
        "charts_generated": has_charts,
        "sampled": ctx["n_sampled"],
        "cohort_size": ctx["n_total"],
    }, indent=2))


def main():
    args = sys.argv[1:]
    if len(args) < 1:
        print(__doc__)
        sys.exit(2)
    cmd, *rest = args
    if cmd == "generate" and 2 <= len(rest) <= 3:
        no_charts = "--no-charts" in rest
        positional = [a for a in rest if not a.startswith("--")]
        if len(positional) != 2:
            print(__doc__)
            sys.exit(2)
        cmd_generate(positional[0], positional[1], no_charts=no_charts)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
