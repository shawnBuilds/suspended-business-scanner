import sys
import time
import json
from typing import Any, Dict, List

import gspread
import os

# Ensure project root is on sys.path so 'scripts.*' imports work when run directly
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_CURRENT_DIR)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)
from scripts.config import CONTROLS, CITY_PRESETS
from scripts.json_to_csv import save_city_snapshot
from scripts.helpers import (
    apply_city_preset,
    load_env_or_exit,
    authorize_client,
    fetch_place_details,
    area_insights_compute,
    map_place_to_row,
    select_matching_keywords,
    find_place_insights_under_cap,
    gather_all_under_cap_across_types,
)
from scripts.sheets import ensure_worksheet, required_headers, assert_raw_tab_or_exit, get_existing_place_ids, run_test_append_dummy_row, get_recipients
from scripts.send_email import send_weekly_summary_email


def compute_area_insights_rows(values: Dict[str, str]) -> List[List[Any]]:
    # Build location filter
    mode = CONTROLS.get("area_insights_location_mode", "circle")
    if mode == "circle":
        location_filter = {
            "circle": {
                "radius": int(CONTROLS.get("area_insights_circle_radius_m", 10000)),
                "latLng": {
                    "latitude": CONTROLS["places_center_lat"],
                    "longitude": CONTROLS["places_center_lng"],
                },
            }
        }
    else:
        print(f"[AreaInsights] Unsupported location mode '{mode}' in this runner.")
        return []

    # Type filter (required by API). Fallbacks: places_type → places_keyword → ["restaurant"]
    types = CONTROLS.get("area_insights_types")
    if not types or not isinstance(types, list) or len(types) == 0:
        fallback_type = CONTROLS.get("places_type")
        if not fallback_type:
            kw = CONTROLS.get("places_keyword")
            if kw and isinstance(kw, str) and kw.strip():
                fallback_type = kw.strip()
        if not fallback_type:
            fallback_type = "restaurant"
        types = [fallback_type]
        if CONTROLS.get("area_log_summary"):
            print(f"[AreaInsights] Using type fallback includedTypes={types}")
    # Optional shuffle of types
    try:
        from scripts.helpers import shuffled_types as _shuffled_types
        ordered_types = _shuffled_types(types, CONTROLS)
    except Exception:
        ordered_types = list(types)
    type_filter = {"includedTypes": ordered_types}

    # If mode == count, iterate statuses and log counts
    aimode = CONTROLS.get("area_insights_mode", "count")
    if aimode == "count":
        statuses = [
            "OPERATING_STATUS_PERMANENTLY_CLOSED",
            "OPERATING_STATUS_TEMPORARILY_CLOSED",
            "OPERATING_STATUS_OPERATIONAL",
        ]
        results: Dict[str, int] = {}
        for st in statuses:
            data = area_insights_compute(
                values,
                insights=["INSIGHT_COUNT"],
                location_filter=location_filter,
                type_filter=type_filter,
                operating_status=[st],
            )
            count_str = data.get("count") or "0"
            try:
                results[st] = int(count_str)
            except Exception:
                results[st] = 0
            if CONTROLS.get("area_log_summary"):
                print(f"[AreaInsights][Count] {st}={results[st]}")
        if CONTROLS.get("area_log_summary"):
            print("[AreaInsights][Count] summary={" + ", ".join([f"{k}:{results[k]}" for k in statuses]) + "}")
        return []

    # mode == places: fetch IDs, then fetch details and optionally write
    operating_status = CONTROLS.get("area_insights_operating_status") or [
        "OPERATING_STATUS_PERMANENTLY_CLOSED",
        "OPERATING_STATUS_TEMPORARILY_CLOSED",
    ]
    # Reflight with counts to respect cap and get place insights using helpers
    max_per = int(CONTROLS.get("area_max_places_per_request", 100))
    working_types: List[str] = list(type_filter.get("includedTypes", []))
    # Choose strategy: gather-all vs single-batch-under-cap
    if bool(CONTROLS.get("area_enable_gather_all_types", False)):
        place_insights = gather_all_under_cap_across_types(
            values=values,
            location_filter=location_filter,
            included_types=working_types,
            operating_status=operating_status,
            max_per=max_per,
        )
    else:
        place_insights = find_place_insights_under_cap(
            values=values,
            location_filter=location_filter,
            included_types=working_types,
            operating_status=operating_status,
            max_per=max_per,
        )

    # Fetch details up to overall max
    details: List[Dict[str, Any]] = []
    overall_max = int(CONTROLS.get("area_insights_overall_max", 500))
    pause = float(CONTROLS.get("area_details_pause_secs", 0.1))
    for idx, pi in enumerate(place_insights):
        if len(details) >= overall_max:
            break
        place_resource = pi.get("place")
        if not place_resource:
            continue
        d = fetch_place_details(values, place_resource)
        if d:
            details.append(d)
        if pause > 0:
            time.sleep(pause)

    if CONTROLS.get("area_log_summary"):
        print(f"[AreaInsights][Details] fetched={len(details)}")

    # Write closed places to sheet
    if not details:
        print("[AreaInsights] No details fetched; nothing to prepare.")
        return []

    # Optionally print a few sample details
    sample_n = int(CONTROLS.get("area_log_details_sample_count", 0) or 0)
    if sample_n > 0:
        print("[AreaInsights][Details][Sample]")
        for p in details[:sample_n]:
            dn = (p.get("displayName") or {}).get("text") if isinstance(p.get("displayName"), dict) else p.get("displayName")
            bs = p.get("businessStatus")
            rt = p.get("rating")
            ur = p.get("userRatingCount")
            addr = p.get("formattedAddress")
            loc = p.get("location") or {}
            lat = loc.get("latitude")
            lng = loc.get("longitude")
            tps = ",".join(p.get("types") or [])
            print({
                "name": dn,
                "status": bs,
                "rating": rt,
                "userRatingCount": ur,
                "address": addr,
                "lat": lat,
                "lng": lng,
                "types": tps,
            })

    # Map and append to Sheets when configured
    # Use intersection between each place's types and the allowed types for more specific keywords
    allowed_types = list(types)
    rows: List[List[Any]] = []
    write_only_closed = bool(CONTROLS.get("area_write_only_closed", True))
    for p in details:
        if write_only_closed:
            bs = p.get("businessStatus")
            # Only temporarily closed per new requirement
            if bs != "CLOSED_TEMPORARILY":
                continue
        specific_kw = select_matching_keywords(p.get("types") or [], allowed_types)
        rows.append(map_place_to_row(p, specific_kw, None, None))
    if not rows:
        print("[AreaInsights] No rows prepared.")
        return []
    return rows


def write_rows_to_sheet(values: Dict[str, str], spreadsheet_id: str, city_name: str, tab_title: str, rows: List[List[Any]]) -> int:
    if not rows:
        return 0
    if not bool(CONTROLS.get("area_insights_write_enabled", True)):
        print(f"[AreaInsights] Write disabled by control. Prepared {len(rows)} rows.")
        return 0
    if not spreadsheet_id:
        print("[AreaInsights] Missing SPREADSHEET_ID; skipping write.")
        return 0
    assert_raw_tab_or_exit(tab_title)

    client = authorize_client(values)
    sh = client.open_by_key(spreadsheet_id)
    ws = ensure_worksheet(sh, tab_title, required_headers())

    existing_ids = get_existing_place_ids(ws)
    unique_rows: List[List[Any]] = []
    seen_batch: set[str] = set()
    for r in rows:
        pid = r[0]
        if not pid:
            continue
        if pid in existing_ids or pid in seen_batch:
            continue
        seen_batch.add(pid)
        unique_rows.append(r)

    if not unique_rows:
        print("[AreaInsights] No new unique rows to append (deduped).")
        return 0

    if bool(CONTROLS.get("snapshot_enable", True)):
        try:
            headers = required_headers() if bool(CONTROLS.get("snapshot_include_headers", True)) else None
            base_dir = CONTROLS.get("snapshot_base_dir") or "."
            snap_path = save_city_snapshot(city_name, unique_rows, headers=headers, base_dir=base_dir)
            if CONTROLS.get("area_log_summary"):
                print(f"[Snapshot] Wrote CSV snapshot before append: {snap_path}")
        except Exception as e:
            print(f"[Snapshot][Warning] Failed to write snapshot: {e}")

    ws.append_rows(unique_rows, value_input_option="RAW")
    appended_n = len(unique_rows)
    print(f"[AreaInsights] Appended {appended_n} new rows to '{tab_title}'.")
    return appended_n


def run_all_cities(values: Dict[str, str], spreadsheet_id: str) -> None:
    # Optional: run for all configured cities, compute first, then write once per city
    city_names = CONTROLS.get("cities_list") or list(CITY_PRESETS.keys())
    counts_by_city: Dict[str, int] = {c: 0 for c in city_names}
    prepared_rows_by_city: Dict[str, List[List[Any]]] = {}
    for city in city_names:
        CONTROLS["city_name"] = city
        apply_city_preset(CONTROLS)
        if CONTROLS.get("area_log_summary"):
            print(f"[Runner] All-cities mode: computing Area Insights for {city}")
        rows: List[List[Any]] = []
        if CONTROLS.get("area_insights_enable"):
            rows = compute_area_insights_rows(values)
        prepared_rows_by_city[city] = rows
    # Now write sequentially per city
    for city in city_names:
        tab_title = CITY_PRESETS.get(city, {}).get("tab", f"{city}_Raw")
        rows = prepared_rows_by_city.get(city) or []
        appended = write_rows_to_sheet(values, spreadsheet_id, city, tab_title, rows)
        counts_by_city[city] = counts_by_city.get(city, 0) + int(appended or 0)
    # Send one email after all cities (if enabled)
    if bool(CONTROLS.get("notify_email_after_write_enable")):
        try:
            client = authorize_client(values)
            sh = client.open_by_key(spreadsheet_id)
            rows_recips = get_recipients(sh, "Recipients")
            to_emails = CONTROLS.get("notify_email_after_write_to_emails") or [r.get("email_address") for r in rows_recips if r.get("email_address")]
        except Exception as e:
            print(f"[Notify] Failed to read recipients: {e}", file=sys.stderr)
            to_emails = []
        if to_emails:
            sheet_link = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
            api_key = values.get("SENDGRID_API_KEY") or ""
            from_email = values.get("FROM_EMAIL") or ""
            if not api_key or not from_email:
                print("[Notify] Missing SENDGRID_API_KEY or FROM_EMAIL in .env; skipping email.")
            else:
                # Map counts to expected template keys
                mapped_counts = {
                    "Chattanooga": counts_by_city.get("Chattanooga", 0),
                    "Medellin": counts_by_city.get("Medellin", 0),
                    "Santa Cruz": counts_by_city.get("Santa Cruz", 0),
                }
                try:
                    send_weekly_summary_email(
                        api_key=api_key,
                        from_email=from_email,
                        to_emails=to_emails,
                        counts=mapped_counts,
                        sheet_link=sheet_link,
                    )
                    print(f"[Notify] Sent summary email to {len(to_emails)} recipient(s).")
                except Exception as e:
                    print(f"[Notify] Failed to send email: {e}", file=sys.stderr)


def main() -> None:
    values = load_env_or_exit()
    spreadsheet_id = values.get("SPREADSHEET_ID")
    if not spreadsheet_id:
        print("Missing SPREADSHEET_ID in .env", file=sys.stderr)
        sys.exit(1)

    # Optional: run for all configured cities, compute first, then write once per city
    if bool(CONTROLS.get("cities_run_all")):
        run_all_cities(values, spreadsheet_id)
        return

    # Single-city mode: apply preset and optionally override tab via .env RAW_TAB
    apply_city_preset(CONTROLS)

    authorize_client(values)

    worksheet_title = (values.get("RAW_TAB") or CONTROLS["raw_tab_default"]).strip()
    # Optional: isolated email test
    if bool(CONTROLS.get("notify_email_test_enable")):
        try:
            client = authorize_client(values)
            sh = client.open_by_key(spreadsheet_id)
        except Exception as e:
            print(f"[EmailTest] Failed to open spreadsheet: {e}", file=sys.stderr)
            sys.exit(1)

        # Determine recipients: controls override -> Recipients sheet
        to_emails = CONTROLS.get("notify_email_test_to_emails") or []
        if not to_emails:
            try:
                from scripts.sheets import get_recipients
                rows = get_recipients(sh, "Recipients")
                to_emails = [r.get("email_address") for r in rows if r.get("email_address")]
            except Exception as e:
                print(f"[EmailTest] Failed to read recipients: {e}", file=sys.stderr)
                to_emails = []
        if not to_emails:
            print("[EmailTest] No email recipients found; aborting test.")
            return

        counts = CONTROLS.get("notify_email_test_counts") or {
            "Chattanooga": 0,
            "Medellin": 0,
            "Santa Cruz": 0,
        }
        sheet_link = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"

        api_key = values.get("SENDGRID_API_KEY") or ""
        from_email = values.get("FROM_EMAIL") or ""
        if not api_key or not from_email:
            print("[EmailTest] Missing SENDGRID_API_KEY or FROM_EMAIL in .env", file=sys.stderr)
            sys.exit(1)

        try:
            send_weekly_summary_email(
                api_key=api_key,
                from_email=from_email,
                to_emails=to_emails,
                counts=counts,
                sheet_link=sheet_link,
            )
            print(f"[EmailTest] Sent test summary email to {len(to_emails)} recipient(s).")
        except Exception as e:
            print(f"[EmailTest] Failed to send: {e}", file=sys.stderr)

    # Deprecated tests are disabled


if __name__ == "__main__":
    main()


