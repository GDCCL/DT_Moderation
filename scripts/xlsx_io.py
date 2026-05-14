#!/usr/bin/env python3
"""Tiny xlsx CLI for the moderation slash-commands.

Usage:
  xlsx_io.py columns <file>
  xlsx_io.py rows <file> <sheet>
  xlsx_io.py learner-rows <file> [<sheet>]
  xlsx_io.py set <file> <sheet> <row> <column> <value>

Notes:
  * Row indices are 1-based and match the spreadsheet view (row 1 is the header).
  * <column> may be a header name (whitespace-trimmed, case-sensitive match against row 1) or a letter (A, B, ...).
  * `learner-rows` auto-picks a sheet whose header row contains both `Name` and `ULN` if no sheet is given,
    and filters to rows where ULN is a 10-digit integer and Name is non-empty. Use this in preference to
    `rows` for moderation flows; use `rows` when you genuinely want every non-empty row.
  * For `set`, a value of `@<path>` reads the cell value from that UTF-8 file (trailing newline trimmed).
    Use this for multi-paragraph comments so you don't have to shell-quote newlines.
  * All output is JSON to stdout so the calling chat can parse it.
"""
import json
import sys
from pathlib import Path

try:
    from openpyxl import load_workbook
    from openpyxl.utils import column_index_from_string, get_column_letter
except ImportError:
    print(json.dumps({"error": "openpyxl not installed. Run: pip install openpyxl"}))
    sys.exit(1)


def _header_row(ws):
    try:
        return [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    except StopIteration:
        return []


def _norm(h):
    return h.strip() if isinstance(h, str) else h


def _norm_headers(raw):
    return [_norm(h) for h in raw]


def _is_valid_uln(value):
    if value is None:
        return False
    s = str(value).strip()
    return s.isdigit() and len(s) == 10


def _records(ws, headers):
    rows = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if all(v is None for v in row):
            continue
        rec = {"_row": i}
        for col_idx, (h, v) in enumerate(zip(headers, row), start=1):
            key = h if h else f"_col{col_idx}"
            rec[key] = v
        rows.append(rec)
    return rows


def cmd_columns(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    out = {name: _header_row(wb[name]) for name in wb.sheetnames}
    print(json.dumps(out, indent=2, default=str))


def cmd_rows(path, sheet):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    headers = _norm_headers(_header_row(ws))
    print(json.dumps(_records(ws, headers), indent=2, default=str))


def _pick_sheet(wb):
    def has_name_and_uln(name):
        headers_lower = {h.strip().lower() for h in _header_row(wb[name]) if isinstance(h, str)}
        return "name" in headers_lower and "uln" in headers_lower

    candidates = [name for name in wb.sheetnames if has_name_and_uln(name)]
    if not candidates:
        return None
    preferred = [c for c in candidates if any(t in c.lower() for t in ("learner", "grade"))]
    return preferred[0] if preferred else candidates[0]


def cmd_learner_rows(path, sheet=None):
    wb = load_workbook(path, read_only=True, data_only=True)
    if sheet is None:
        sheet = _pick_sheet(wb)
        if sheet is None:
            print(json.dumps({"error": "no sheet contains both 'Name' and 'ULN' headers", "sheets": wb.sheetnames}))
            sys.exit(1)
    elif sheet not in wb.sheetnames:
        print(json.dumps({"error": f"sheet '{sheet}' not found", "sheets": wb.sheetnames}))
        sys.exit(1)
    ws = wb[sheet]
    raw_headers = _header_row(ws)
    headers = _norm_headers(raw_headers)
    rows = []
    for rec in _records(ws, headers):
        if not _is_valid_uln(rec.get("ULN")):
            continue
        name = rec.get("Name")
        if not (isinstance(name, str) and name.strip()):
            continue
        rec["Name"] = name.strip()
        rec["ULN"] = str(rec["ULN"]).strip()
        rows.append(rec)
    out = {"sheet": sheet, "headers": headers, "raw_headers": raw_headers, "rows": rows}
    print(json.dumps(out, indent=2, default=str))


def cmd_set(path, sheet, row, column, value):
    if isinstance(value, str) and value.startswith("@"):
        value = Path(value[1:]).read_text(encoding="utf-8").rstrip("\n")
    wb = load_workbook(path)
    ws = wb[sheet]
    if column.isalpha():
        col_idx = column_index_from_string(column)
    else:
        raw_headers = _header_row(ws)
        target = column.strip()
        col_idx = None
        for idx, h in enumerate(raw_headers, start=1):
            if isinstance(h, str) and h.strip() == target:
                col_idx = idx
                break
        if col_idx is None:
            print(json.dumps({"error": f"column '{column}' not found", "headers": raw_headers}))
            sys.exit(1)
    ws.cell(row=int(row), column=col_idx).value = value
    wb.save(path)
    preview = value if len(value) <= 80 else value[:77] + "..."
    print(json.dumps({"ok": True, "cell": f"{get_column_letter(col_idx)}{row}", "value": preview}))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    cmd, *rest = args
    if cmd == "columns" and len(rest) == 1:
        cmd_columns(rest[0])
    elif cmd == "rows" and len(rest) == 2:
        cmd_rows(*rest)
    elif cmd == "learner-rows" and 1 <= len(rest) <= 2:
        cmd_learner_rows(*rest)
    elif cmd == "set" and len(rest) == 5:
        cmd_set(*rest)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
