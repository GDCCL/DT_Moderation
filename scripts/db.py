#!/usr/bin/env python3
"""SQLite-backed analytics for the moderation tool.

The DB lives at `analytics.db` in the repo root and is committed. Learner
identifiers are hashed (salted SHA-256) with the salt from `.env`. The salt
is gitignored and must be shared with collaborators out of band, otherwise
hashes won't match across machines.

Usage:
  db.py init                              # create .env + analytics.db
  db.py hash <uln>                        # print hashed key for one ULN
  db.py record-pass < payload.json        # write a moderation pass (JSON via stdin)
  db.py summary <module> [<cohort>]       # pre-canned aggregate report (JSON)
  db.py query --sql "<SQL>"               # read-only ad-hoc SELECT (JSON rows)

Payload shape for record-pass:
  {
    "module_code": "DT604",
    "cohort_code": "Sep23",
    "overall_summary": "...",
    "learners": [
      {"uln": "1234567890", "part_a": 65, "part_b": 70,
       "total": 67.5, "band": "Merit", "was_sampled": true}
    ],
    "themes": [
      {"theme": "criterion-3-strong", "count": 4,
       "notes": "Distinctions consistently evidence criterion 3."}
    ]
  }
"""
import hashlib
import json
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "analytics.db"
ENV_PATH = ROOT / ".env"

SCHEMA = """
CREATE TABLE IF NOT EXISTS moderation_passes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module_code TEXT NOT NULL,
  cohort_code TEXT NOT NULL,
  run_at TEXT NOT NULL DEFAULT (datetime('now')),
  sample_size INTEGER NOT NULL,
  overall_summary TEXT
);

CREATE TABLE IF NOT EXISTS learner_grades (
  pass_id INTEGER NOT NULL REFERENCES moderation_passes(id) ON DELETE CASCADE,
  learner_key TEXT NOT NULL,
  module_code TEXT NOT NULL,
  cohort_code TEXT NOT NULL,
  part_a REAL,
  part_b REAL,
  total REAL,
  band TEXT,
  was_sampled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS moderator_themes (
  pass_id INTEGER NOT NULL REFERENCES moderation_passes(id) ON DELETE CASCADE,
  module_code TEXT NOT NULL,
  cohort_code TEXT NOT NULL,
  theme TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  lo_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_grades_module  ON learner_grades(module_code);
CREATE INDEX IF NOT EXISTS idx_grades_learner ON learner_grades(learner_key);
CREATE INDEX IF NOT EXISTS idx_themes_module  ON moderator_themes(module_code);
"""


def load_salt():
    if not ENV_PATH.exists():
        sys.exit("Missing .env. Run: python3 scripts/db.py init")
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line.startswith("MODERATION_HASH_SALT="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if not value:
                sys.exit("MODERATION_HASH_SALT in .env is empty.")
            return value
    sys.exit("MODERATION_HASH_SALT not found in .env")


def hash_uln(uln, salt):
    return hashlib.sha256((salt + str(uln).strip()).encode("utf-8")).hexdigest()[:16]


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    # Migration: add lo_id to existing moderator_themes tables that pre-date it.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(moderator_themes)").fetchall()]
    if "lo_id" not in cols:
        conn.execute("ALTER TABLE moderator_themes ADD COLUMN lo_id TEXT")
        conn.commit()
    return conn


def cmd_init():
    created = []
    if not ENV_PATH.exists():
        salt = secrets.token_hex(32)
        ENV_PATH.write_text(
            "# Salt used to hash learner ULNs in analytics.db.\n"
            "# Share this value with collaborators OUT OF BAND — do not commit.\n"
            f"MODERATION_HASH_SALT={salt}\n"
        )
        created.append(".env (with a freshly generated salt)")
    if not DB_PATH.exists():
        connect().close()
        created.append("analytics.db")
    print(json.dumps({"ok": True, "created": created or "nothing (already initialised)"}, indent=2))


def cmd_hash(uln):
    print(hash_uln(uln, load_salt()))


def cmd_record_pass():
    payload = json.loads(sys.stdin.read())
    salt = load_salt()
    conn = connect()
    cur = conn.cursor()
    learners = payload.get("learners", [])
    themes = payload.get("themes", [])
    sample_size = sum(1 for l in learners if l.get("was_sampled"))
    cur.execute(
        "INSERT INTO moderation_passes (module_code, cohort_code, sample_size, overall_summary) "
        "VALUES (?, ?, ?, ?)",
        (payload["module_code"], payload["cohort_code"], sample_size, payload.get("overall_summary")),
    )
    pass_id = cur.lastrowid
    for l in learners:
        cur.execute(
            "INSERT INTO learner_grades (pass_id, learner_key, module_code, cohort_code, "
            "part_a, part_b, total, band, was_sampled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                pass_id,
                hash_uln(l["uln"], salt),
                payload["module_code"],
                payload["cohort_code"],
                l.get("part_a"),
                l.get("part_b"),
                l.get("total"),
                l.get("band"),
                1 if l.get("was_sampled") else 0,
            ),
        )
    for t in themes:
        cur.execute(
            "INSERT INTO moderator_themes (pass_id, module_code, cohort_code, theme, count, notes, lo_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                pass_id,
                payload["module_code"],
                payload["cohort_code"],
                t["theme"],
                int(t.get("count", 1)),
                t.get("notes"),
                t.get("lo_id"),
            ),
        )
    conn.commit()
    conn.close()
    print(json.dumps({"ok": True, "pass_id": pass_id, "learners": len(learners), "themes": len(themes)}))


def cmd_summary(module, cohort=None):
    conn = connect()
    conn.row_factory = sqlite3.Row
    where = "module_code = ?"
    args = [module]
    if cohort:
        where += " AND cohort_code = ?"
        args.append(cohort)

    overall = conn.execute(
        f"SELECT COUNT(*) AS n, AVG(total) AS mean_total, "
        f"       MIN(total) AS min_total, MAX(total) AS max_total, "
        f"       SUM(was_sampled) AS sampled "
        f"FROM learner_grades WHERE {where}",
        args,
    ).fetchone()

    bands = conn.execute(
        f"SELECT band, COUNT(*) AS n FROM learner_grades WHERE {where} "
        f"GROUP BY band ORDER BY n DESC",
        args,
    ).fetchall()

    themes = conn.execute(
        f"SELECT theme, SUM(count) AS total_count FROM moderator_themes WHERE {where} "
        f"GROUP BY theme ORDER BY total_count DESC LIMIT 20",
        args,
    ).fetchall()

    by_lo = conn.execute(
        f"SELECT lo_id, SUM(count) AS total_count, COUNT(DISTINCT theme) AS distinct_themes "
        f"FROM moderator_themes WHERE {where} AND lo_id IS NOT NULL "
        f"GROUP BY lo_id ORDER BY total_count DESC",
        args,
    ).fetchall()

    passes = conn.execute(
        f"SELECT id, cohort_code, run_at, sample_size FROM moderation_passes WHERE {where} "
        f"ORDER BY run_at DESC LIMIT 20",
        args,
    ).fetchall()

    result = {
        "scope": {"module": module, "cohort": cohort},
        "overall": dict(overall) if overall else {},
        "bands": [dict(b) for b in bands],
        "top_themes": [dict(t) for t in themes],
        "themes_by_lo": [dict(r) for r in by_lo],
        "recent_passes": [dict(p) for p in passes],
    }
    print(json.dumps(result, indent=2, default=str))


def cmd_query(sql):
    sql_lower = sql.strip().lower()
    if not sql_lower.startswith("select"):
        sys.exit("Only SELECT queries are permitted via db.py query.")
    forbidden = ("attach", "pragma", "insert", "update", "delete", "drop", "alter", "replace")
    if any(w in sql_lower for w in forbidden):
        sys.exit("Query contains a forbidden keyword.")
    conn = connect()
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql).fetchall()]
    print(json.dumps(rows, indent=2, default=str))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    cmd, *rest = args
    if cmd == "init" and not rest:
        cmd_init()
    elif cmd == "hash" and len(rest) == 1:
        cmd_hash(rest[0])
    elif cmd == "record-pass" and not rest:
        cmd_record_pass()
    elif cmd == "summary" and 1 <= len(rest) <= 2:
        cmd_summary(*rest)
    elif cmd == "query" and len(rest) == 2 and rest[0] == "--sql":
        cmd_query(rest[1])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
