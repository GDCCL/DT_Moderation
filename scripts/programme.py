#!/usr/bin/env python3
"""Read-only access to the programme catalogue at modules/programme.json.

Usage:
  programme.py list                    # programme code, title, and module codes
  programme.py module <code>           # full record for one module (JSON)
  programme.py los <code>              # learning outcomes for one module (JSON)
  programme.py challenge <code>        # module challenges (Part A/B titles, weightings, LOs)

All output is JSON for the calling chat to parse.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "modules" / "programme.json"


def load():
    if not PATH.exists():
        sys.exit(f"Missing {PATH}. Place the programme catalogue there.")
    return json.loads(PATH.read_text())


def find_module(data, code):
    for m in data["modules"]:
        if m["code"].upper() == code.upper():
            return m
    sys.exit(f"Module '{code}' not found. Known: {', '.join(m['code'] for m in data['modules'])}")


def cmd_list():
    data = load()
    out = {
        "code": data["code"],
        "title": data["title"],
        "modules": [{"code": m["code"], "title": m["title"]} for m in data["modules"]],
    }
    print(json.dumps(out, indent=2))


def cmd_module(code):
    print(json.dumps(find_module(load(), code), indent=2))


def cmd_los(code):
    print(json.dumps(find_module(load(), code).get("learningOutcomes", []), indent=2))


def cmd_challenge(code):
    print(json.dumps(find_module(load(), code).get("moduleChallenge", []), indent=2))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    cmd, *rest = args
    if cmd == "list" and not rest:
        cmd_list()
    elif cmd == "module" and len(rest) == 1:
        cmd_module(rest[0])
    elif cmd == "los" and len(rest) == 1:
        cmd_los(rest[0])
    elif cmd == "challenge" and len(rest) == 1:
        cmd_challenge(rest[0])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
