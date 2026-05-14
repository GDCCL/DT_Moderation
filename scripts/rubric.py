#!/usr/bin/env python3
"""Read-only access to the level rubrics.

Module code → level mapping is by the second digit of the code:
  DT4xx → L4
  DT5xx → L5
  DT6xx → L6

Usage:
  rubric.py level <module_code>                     # print "L4"/"L5"/"L6"
  rubric.py for-module <module_code>                # full rubric for the module's level (JSON)
  rubric.py level-rubric <L4|L5|L6>                 # full rubric for a level (JSON)
  rubric.py criterion <module_code> "<criterion>"   # all bands for one criterion at the module's level
  rubric.py band <module_code> <total>              # which rubric band a percentage falls into
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUBRICS_DIR = ROOT / "rubrics"

BANDS = [
    ("Fail",         0,   31.999),
    ("Insufficient", 32,  39.999),
    ("Satisfactory", 40,  49.999),
    ("Good",         50,  59.999),
    ("Very Good",    60,  69.999),
    ("Excellent",    70,  85.000),
    ("Outstanding",  85.001, 100),
]


def level_for(code):
    m = re.match(r"^DT([4-6])\d\d$", code.upper())
    if not m:
        sys.exit(f"Module code '{code}' is not in the form DT[4-6]\\d\\d.")
    return f"L{m.group(1)}"


def load_level(level):
    path = RUBRICS_DIR / f"{level}.json"
    if not path.exists():
        sys.exit(f"Rubric file {path} not found.")
    return json.loads(path.read_text())


def normalise(s):
    return re.sub(r"[\s\-]+", " ", s.strip().lower())


def cmd_level(code):
    print(level_for(code))


def cmd_for_module(code):
    print(json.dumps(load_level(level_for(code)), indent=2))


def cmd_level_rubric(level):
    print(json.dumps(load_level(level), indent=2))


def cmd_criterion(code, criterion):
    data = load_level(level_for(code))
    target = normalise(criterion)
    for c in data["rubric"]:
        if normalise(c["criterion"]) == target:
            print(json.dumps(c, indent=2))
            return
    available = [c["criterion"] for c in data["rubric"]]
    sys.exit(f"Criterion '{criterion}' not found. Available: {available}")


def cmd_band(code, total):
    try:
        t = float(total)
    except ValueError:
        sys.exit(f"Total '{total}' is not numeric.")
    for name, lo, hi in BANDS:
        if lo <= t <= hi:
            print(json.dumps({"module": code.upper(), "level": level_for(code),
                              "total": t, "band": name}))
            return
    sys.exit(f"Total {t} did not match any band.")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    cmd, *rest = args
    if cmd == "level" and len(rest) == 1:
        cmd_level(rest[0])
    elif cmd == "for-module" and len(rest) == 1:
        cmd_for_module(rest[0])
    elif cmd == "level-rubric" and len(rest) == 1:
        cmd_level_rubric(rest[0])
    elif cmd == "criterion" and len(rest) == 2:
        cmd_criterion(*rest)
    elif cmd == "band" and len(rest) == 2:
        cmd_band(*rest)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
