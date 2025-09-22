from typing import Any, Dict, List

import sys
import gspread


def ensure_worksheet(spreadsheet: gspread.Spreadsheet, title: str, headers: List[str]) -> gspread.Worksheet:
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=100, cols=max(10, len(headers)))
        if headers:
            ws.update('1:1', [headers])
    # If worksheet exists but empty, add headers if first row is blank
    if headers:
        first_row = ws.row_values(1)
        if not first_row:
            ws.update('1:1', [headers])
    return ws


def required_headers() -> List[str]:
    return [
        "place_id",
        "name",
        "business_status",
        "business_address",
        "lat",
        "lng",
        "types",
        "rating",
        "user_ratings_total",
        "keyword",
        "grid_lat",
        "grid_lng",
    ]


def assert_raw_tab_or_exit(tab_name: str) -> None:
    if not tab_name.endswith("_Raw"):
        print("Refusing to write: target tab must end with '_Raw' to avoid *_View tabs.", file=sys.stderr)
        sys.exit(1)


def get_existing_place_ids(ws: gspread.Worksheet) -> set[str]:
    try:
        col = ws.col_values(1) or []
    except Exception:
        return set()
    if col and isinstance(col[0], str) and col[0].strip().lower() == "place_id":
        col = col[1:]
    return set(v for v in col if v)


def run_test_append_dummy_row(client: gspread.Client, spreadsheet_id: str, tab_name: str, dummy_row_func) -> None:
    sh = client.open_by_key(spreadsheet_id)
    ws = ensure_worksheet(sh, tab_name, required_headers())
    ws.append_row(dummy_row_func(), value_input_option="RAW")
    print(f"[append_dummy_row] Appended row to '{tab_name}' in spreadsheet {spreadsheet_id}.")


# Recipients utilities
def get_recipients(spreadsheet: gspread.Spreadsheet, tab_name: str = "Recipients") -> List[Dict[str, str]]:
    """Read recipients from a worksheet.

    Expects header row with: name, email_address, whatsapp_number
    Returns a list of dicts with those keys. Skips blank or incomplete rows.
    """
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        print(f"[Recipients] Worksheet '{tab_name}' not found.", file=sys.stderr)
        return []
    try:
        values = ws.get_all_values()
    except Exception:
        return []
    if not values:
        return []
    headers = [h.strip().lower() for h in (values[0] or [])]
    idx = {h: i for i, h in enumerate(headers)}
    required = ["name", "email_address", "whatsapp_number"]
    for r in required:
        if r not in idx:
            print(f"[Recipients] Missing header '{r}' in '{tab_name}'.", file=sys.stderr)
            return []
    rows: List[Dict[str, str]] = []
    for raw in values[1:]:
        try:
            name = (raw[idx["name"]] or "").strip()
            email = (raw[idx["email_address"]] or "").strip()
            whatsapp = (raw[idx["whatsapp_number"]] or "").strip()
        except Exception:
            continue
        if not name and not email and not whatsapp:
            continue
        if not email and not whatsapp:
            # Require at least one contact method
            continue
        rows.append({
            "name": name,
            "email_address": email,
            "whatsapp_number": whatsapp,
        })
    return rows

