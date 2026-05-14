#!/usr/bin/env python3
"""Tiny xlsx CLI for the moderation slash-commands.

Usage:
  xlsx_io.py columns <file>
  xlsx_io.py rows <file> <sheet>
  xlsx_io.py set <file> <sheet> <row> <column> <value>

Notes:
  * Row indices are 1-based and match the spreadsheet view (row 1 is the header).
  * <column> may be a header name (case-sensitive match against row 1) or a letter (A, B, ...).
  * All output is JSON to stdout so the calling chat can parse it.
"""
import json
import sys

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


def cmd_columns(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    out = {name: _header_row(wb[name]) for name in wb.sheetnames}
    print(json.dumps(out, indent=2, default=str))


def cmd_rows(path, sheet):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    headers = _header_row(ws)
    rows = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if all(v is None for v in row):
            continue
        rec = {"_row": i}
        for h, v in zip(headers, row):
            rec[h if h is not None else f"_col{headers.index(h) + 1}"] = v
        rows.append(rec)
    print(json.dumps(rows, indent=2, default=str))


def cmd_set(path, sheet, row, column, value):
    wb = load_workbook(path)
    ws = wb[sheet]
    if column.isalpha():
        col_idx = column_index_from_string(column)
    else:
        headers = _header_row(ws)
        try:
            col_idx = headers.index(column) + 1
        except ValueError:
            print(json.dumps({"error": f"column '{column}' not found", "headers": headers}))
            sys.exit(1)
    ws.cell(row=int(row), column=col_idx).value = value
    wb.save(path)
    print(json.dumps({"ok": True, "cell": f"{get_column_letter(col_idx)}{row}", "value": value}))


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
    elif cmd == "set" and len(rest) == 5:
        cmd_set(*rest)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
