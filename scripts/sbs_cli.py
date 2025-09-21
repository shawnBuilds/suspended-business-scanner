import sys
import time
import json
from typing import Any, Dict, List

import gspread
from scripts.config import CONTROLS, CITY_PRESETS
from scripts.helpers import (
    apply_city_preset,
    load_env_or_exit,
    authorize_client,
    fetch_place_details,
    area_insights_compute,
    map_place_to_row,
    select_matching_keywords,
)
from scripts.sheets import ensure_worksheet, required_headers, assert_raw_tab_or_exit, get_existing_place_ids, run_test_append_dummy_row


def run_area_insights(values: Dict[str, str]) -> None:
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
        return

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
    type_filter = {"includedTypes": types}

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
        return

    # mode == places: fetch IDs, then fetch details and optionally write
    operating_status = CONTROLS.get("area_insights_operating_status") or [
        "OPERATING_STATUS_PERMANENTLY_CLOSED",
        "OPERATING_STATUS_TEMPORARILY_CLOSED",
    ]
    # Reflight with counts to respect 100-place cap
    max_per = int(CONTROLS.get("area_max_places_per_request", 100))
    # Start with the full type list; progressively reduce if counts exceed cap
    working_types: List[str] = list(type_filter.get("includedTypes", []))
    place_insights: List[Dict[str, Any]] = []
    while working_types:
        # 1) count
        count_data = area_insights_compute(
            values,
            insights=["INSIGHT_COUNT"],
            location_filter=location_filter,
            type_filter={"includedTypes": working_types},
            operating_status=operating_status,
        )
        if "_error" in count_data:
            err = count_data["_error"]
            print(f"[AreaInsights][Count][Error] status={err['status']} body={err['body']}")
            break
        count_str = count_data.get("count") or "0"
        try:
            count_val = int(count_str)
        except Exception:
            count_val = 0
        if CONTROLS.get("area_log_summary"):
            print(f"[AreaInsights][Count] types={working_types} count={count_val}")

        if count_val == 0:
            # Nothing for this set; stop
            break

        if count_val <= max_per:
            # 2) fetch places for this set
            data = area_insights_compute(
                values,
                insights=["INSIGHT_PLACES"],
                location_filter=location_filter,
                type_filter={"includedTypes": working_types},
                operating_status=operating_status,
            )
            if "_error" in data:
                err = data["_error"]
                print(f"[AreaInsights][Places][Error] status={err['status']} body={err['body']}")
                break
            place_insights = data.get("placeInsights") or []
            if CONTROLS.get("area_log_summary"):
                print(f"[AreaInsights][Places] returned={len(place_insights)} for types={working_types}")
            break

        # count_val > max_per → reduce the types list and retry
        if len(working_types) == 1 and CONTROLS.get("area_skip_large_single_type", True):
            if CONTROLS.get("area_log_summary"):
                print(f"[AreaInsights][Count] single type {working_types[0]} exceeds {max_per}; skipping fetch")
            break
        # Drop half of the types (last half) and retry
        drop_n = max(1, len(working_types) // 2)
        working_types = working_types[:-drop_n]
        if CONTROLS.get("area_log_summary"):
            print(f"[AreaInsights][Count] Reducing types; retry with {working_types}")

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
        print("[AreaInsights] No details fetched; nothing to write.")
        return

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
    rows = []
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
        return
    # Write to sheet if spreadsheet_id and a default tab are available
    spreadsheet_id = values.get("SPREADSHEET_ID")
    if not spreadsheet_id:
        print("[AreaInsights] Missing SPREADSHEET_ID; skipping write.")
        return
    if not bool(CONTROLS.get("area_insights_write_enabled", True)):
        print(f"[AreaInsights] Write disabled by control. Prepared {len(rows)} rows.")
        return

    client = authorize_client(values)
    sh = client.open_by_key(spreadsheet_id)
    ws = ensure_worksheet(sh, CONTROLS["raw_tab_default"], required_headers())

    # Deduplicate: skip rows where place_id already exists in sheet
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
        return

    ws.append_rows(unique_rows, value_input_option="RAW")
    print(f"[AreaInsights] Appended {len(unique_rows)} new rows to '{CONTROLS['raw_tab_default']}'.")


def main() -> None:
    values = load_env_or_exit()
    spreadsheet_id = values.get("SPREADSHEET_ID")
    if not spreadsheet_id:
        print("Missing SPREADSHEET_ID in .env", file=sys.stderr)
        sys.exit(1)

    # Optional: run for all configured cities, writing to each city's *_Raw tab
    if bool(CONTROLS.get("cities_run_all")):
        city_names = CONTROLS.get("cities_list") or list(CITY_PRESETS.keys())
        for city in city_names:
            CONTROLS["city_name"] = city
            apply_city_preset(CONTROLS)
            assert_raw_tab_or_exit(CONTROLS["raw_tab_default"])
            if CONTROLS.get("area_log_summary"):
                print(f"[Runner] All-cities mode: running Area Insights for {city} → tab={CONTROLS['raw_tab_default']}")
            if CONTROLS.get("area_insights_enable"):
                run_area_insights(values)
        return

    # Single-city mode (default): apply preset and optionally override tab via .env RAW_TAB
    apply_city_preset(CONTROLS)

    authorize_client(values)

    worksheet_title = (values.get("RAW_TAB") or CONTROLS["raw_tab_default"]).strip()
    assert_raw_tab_or_exit(worksheet_title)

    if CONTROLS.get("area_insights_enable"):
        run_area_insights(values)

    # Deprecated tests are disabled


if __name__ == "__main__":
    main()


