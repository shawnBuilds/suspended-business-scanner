from typing import Any, Dict, List
import random
import hashlib
from datetime import datetime, timezone

import os
import sys
import requests
import gspread
from dotenv import dotenv_values
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request

from scripts.config import CITY_PRESETS, CONTROLS


def apply_city_preset(controls: Dict[str, Any]) -> None:
    city = controls.get("city_name")
    preset = CITY_PRESETS.get(city)
    if not preset:
        print(f"[Controls] Unknown city '{city}'. Please set CONTROLS['city_name'] to one of: {list(CITY_PRESETS.keys())}", file=sys.stderr)
        sys.exit(1)
    controls["places_center_lat"] = preset["lat"]
    controls["places_center_lng"] = preset["lng"]
    controls["raw_tab_default"] = preset["tab"]
    if controls.get("enable_verbose_logging"):
        print(f"[Controls] Applied city preset: {city} → lat={preset['lat']}, lng={preset['lng']}, tab={preset['tab']}")


def load_env_or_exit() -> dict:
    env_path = os.path.join(".env")
    if not os.path.isfile(env_path):
        print(f"Config file not found at: {env_path}. Create a .env at project root.", file=sys.stderr)
        sys.exit(1)
    values = dotenv_values(env_path)
    if not values:
        print("Failed to load values from .env.", file=sys.stderr)
        sys.exit(1)
    return values


def build_service_account_info(values: dict) -> dict:
    return {
        "type": values.get("TYPE", "service_account"),
        "project_id": values.get("PROJECT_ID"),
        "private_key_id": values.get("PRIVATE_KEY_ID"),
        "private_key": (values.get("PRIVATE_KEY") or "").replace("\\n", "\n"),
        "client_email": values.get("CLIENT_EMAIL"),
        "client_id": values.get("CLIENT_ID"),
        "auth_uri": values.get("AUTH_URI"),
        "token_uri": values.get("TOKEN_URI"),
        "auth_provider_x509_cert_url": values.get("AUTH_PROVIDER_X509_CERT_URL"),
        "client_x509_cert_url": values.get("CLIENT_X509_CERT_URL"),
        "universe_domain": values.get("UNIVERSE_DOMAIN", "googleapis.com"),
    }


def validate_service_account_info_or_exit(info: dict) -> None:
    required_fields = [
        "project_id",
        "private_key_id",
        "private_key",
        "client_email",
        "client_id",
        "auth_uri",
        "token_uri",
        "auth_provider_x509_cert_url",
        "client_x509_cert_url",
    ]
    missing = [k for k in required_fields if not info.get(k)]
    if missing:
        print(f"Missing required fields in .env: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def authorize_client(values: dict) -> gspread.Client:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    service_account_info = build_service_account_info(values)
    validate_service_account_info_or_exit(service_account_info)
    try:
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    except Exception as e:
        print(f"Failed to create credentials from .env: {e}", file=sys.stderr)
        sys.exit(1)
    client = gspread.authorize(credentials)
    return client


def fetch_place_details(values: Dict[str, str], place_resource_name: str) -> Dict[str, Any]:
    api_key = values.get("PLACES_API_KEY")
    if not api_key:
        print("Missing PLACES_API_KEY in .env", file=sys.stderr)
        sys.exit(1)
    fields = ",".join([
        "name",
        "id",
        "displayName",
        "formattedAddress",
        "location",
        "types",
        "rating",
        "userRatingCount",
        "businessStatus",
    ])
    url = f"https://places.googleapis.com/v1/{place_resource_name}"
    headers = {
        "X-Goog-Api-Key": api_key,
    }
    params = {"fields": fields}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    try:
        data = resp.json()
    except Exception:
        print(f"Place Details returned non-JSON (status {resp.status_code}) for {place_resource_name}", file=sys.stderr)
        return {}
    if resp.status_code != 200:
        return {}
    return data


def build_area_insights_credentials(values: dict):
    service_account_info = build_service_account_info(values)
    validate_service_account_info_or_exit(service_account_info)
    try:
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    except Exception as e:
        print(f"Failed to create Area Insights credentials: {e}", file=sys.stderr)
        sys.exit(1)
    return credentials


def area_insights_compute(values: Dict[str, str],
                          insights: List[str],
                          location_filter: Dict[str, Any],
                          type_filter: Dict[str, Any] | None,
                          operating_status: List[str] | None,
                          price_levels: List[str] | None = None,
                          rating_filter: Dict[str, Any] | None = None) -> Dict[str, Any]:
    url = "https://areainsights.googleapis.com/v1:computeInsights"
    creds = build_area_insights_credentials(values)
    try:
        creds.refresh(Request())
    except Exception as e:
        print(f"Failed to refresh Area Insights token: {e}", file=sys.stderr)
        sys.exit(1)
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {
        "insights": insights,
        "filter": {
            "locationFilter": location_filter,
        }
    }
    if type_filter:
        body["filter"]["typeFilter"] = type_filter
    if operating_status:
        body["filter"]["operatingStatus"] = operating_status
    if price_levels:
        body["filter"]["priceLevels"] = price_levels
    if rating_filter:
        body["filter"]["ratingFilter"] = rating_filter
    if CONTROLS.get("enable_verbose_logging") or CONTROLS.get("area_log_request_build"):
        print("[AreaInsights][Build] Built request")
        print(f"  url={url}")
        print(f"  body={body}")
    if CONTROLS.get("enable_verbose_logging") or CONTROLS.get("area_log_request_send"):
        print("[AreaInsights][Request] POST")
        print(f"  url={url}")
        print(f"  body={body}")
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    try:
        data = resp.json()
    except Exception:
        print(f"Area Insights returned non-JSON (status {resp.status_code})", file=sys.stderr)
        sys.exit(1)
    if resp.status_code != 200:
        return {"_error": {"status": resp.status_code, "body": data}}
    if CONTROLS.get("enable_verbose_logging") or CONTROLS.get("area_log_response_keys"):
        print(f"[AreaInsights][Response] keys={list(data.keys())}")
    if CONTROLS.get("enable_verbose_logging") and CONTROLS.get("area_log_full_response"):
        import json as _json
        print(f"[AreaInsights][Response] full={_json.dumps(data, ensure_ascii=False)[:4000]}")
    return data



def _parse_count_value(count_data: Dict[str, Any]) -> int:
    """Safely parse the 'count' field from an Area Insights response into an int."""
    count_str = count_data.get("count") or "0"
    try:
        return int(count_str)
    except Exception:
        return 0


def _area_count_for_types(values: Dict[str, str],
                          location_filter: Dict[str, Any],
                          types: List[str],
                          operating_status: List[str] | None) -> Dict[str, Any]:
    return area_insights_compute(
        values,
        insights=["INSIGHT_COUNT"],
        location_filter=location_filter,
        type_filter={"includedTypes": types} if types else None,
        operating_status=operating_status,
    )


def _area_places_for_types(values: Dict[str, str],
                           location_filter: Dict[str, Any],
                           types: List[str],
                           operating_status: List[str] | None) -> Dict[str, Any]:
    return area_insights_compute(
        values,
        insights=["INSIGHT_PLACES"],
        location_filter=location_filter,
        type_filter={"includedTypes": types} if types else None,
        operating_status=operating_status,
    )


def find_place_insights_under_cap(values: Dict[str, str],
                                  location_filter: Dict[str, Any],
                                  included_types: List[str],
                                  operating_status: List[str] | None,
                                  max_per: int) -> List[Dict[str, Any]]:
    """Return placeInsights for a given type list, ensuring count <= max_per.

    Strategy:
    - Compute count for the full list. If <= max_per, fetch places and return.
    - If count exceeds cap, iteratively reduce the working list by half and retry.
    - When reduced to a single type that still exceeds the cap, optionally skip
      or attempt single-type fallbacks across the original order (controlled by CONTROLS).
    - Returns an empty list on errors or when no subset fits under the cap.
    """
    working_types: List[str] = list(included_types or [])
    original_types: List[str] = list(working_types)
    place_insights: List[Dict[str, Any]] = []
    fetched = False

    while working_types and not fetched:
        # 1) Count for current set of types
        count_data = _area_count_for_types(values, location_filter, working_types, operating_status)
        if "_error" in count_data:
            err = count_data["_error"]
            print(f"[AreaInsights][Count][Error] status={err['status']} body={err['body']}")
            break
        count_val = _parse_count_value(count_data)
        if CONTROLS.get("area_log_summary"):
            print(f"[AreaInsights][Count] types={working_types} count={count_val}")

        if count_val == 0:
            # Nothing for this set; stop
            break

        if count_val <= max_per:
            # 2) Fetch places for this set
            data = _area_places_for_types(values, location_filter, working_types, operating_status)
            if "_error" in data:
                err = data["_error"]
                print(f"[AreaInsights][Places][Error] status={err['status']} body={err['body']}")
                break
            place_insights = data.get("placeInsights") or []
            if CONTROLS.get("area_log_summary"):
                print(f"[AreaInsights][Places] returned={len(place_insights)} for types={working_types}")
            fetched = True
            break

        # count_val > max_per → reduce or fallback
        if len(working_types) == 1:
            if CONTROLS.get("area_skip_large_single_type", True):
                if CONTROLS.get("area_log_summary"):
                    print(f"[AreaInsights][Count] single type {working_types[0]} exceeds {max_per}; skipping fetch")
                # Try fallback if enabled: iterate over remaining single types in original order
                if CONTROLS.get("area_enable_single_type_fallback"):
                    if CONTROLS.get("area_log_summary"):
                        print("[AreaInsights][Count] Trying next available single-type fallbacks")
                    for t in original_types:
                        if t == working_types[0]:
                            continue
                        fb_count = _area_count_for_types(values, location_filter, [t], operating_status)
                        if "_error" in fb_count:
                            err = fb_count["_error"]
                            print(f"[AreaInsights][Count][Error] status={err['status']} body={err['body']}")
                            continue
                        fb_val = _parse_count_value(fb_count)
                        if CONTROLS.get("area_log_summary"):
                            print(f"[AreaInsights][Count] types={[t]} count={fb_val}")
                        if fb_val == 0:
                            continue
                        if fb_val <= max_per:
                            data = _area_places_for_types(values, location_filter, [t], operating_status)
                            if "_error" in data:
                                err = data["_error"]
                                print(f"[AreaInsights][Places][Error] status={err['status']} body={err['body']}")
                                continue
                            place_insights = data.get("placeInsights") or []
                            if CONTROLS.get("area_log_summary"):
                                print(f"[AreaInsights][Places] returned={len(place_insights)} for types={[t]}")
                            fetched = True
                            break
                        else:
                            if CONTROLS.get("area_log_summary"):
                                print(f"[AreaInsights][Count] single type {t} exceeds {max_per}; skipping fetch")
                break
            # If not skipping large single type, we would have fetched above; fall through

        # Drop half of the types (last half) and retry
        drop_n = max(1, len(working_types) // 2)
        working_types = working_types[:-drop_n]
        if CONTROLS.get("area_log_summary"):
            print(f"[AreaInsights][Count] Reducing types; retry with {working_types}")

    return place_insights


def gather_all_under_cap_across_types(values: Dict[str, str],
                                      location_filter: Dict[str, Any],
                                      included_types: List[str],
                                      operating_status: List[str] | None,
                                      max_per: int) -> List[Dict[str, Any]]:
    """Accumulate placeInsights by scanning each single type and adding all batches
    whose count <= max_per. Deduplicates by place resource. Stops once the
    aggregated list reaches the overall max configured in CONTROLS.

    Notes:
    - Skips types with count == 0
    - Skips types with count > max_per (honors area_skip_large_single_type semantics)
    - Prints concise logs when area_log_summary is enabled
    """
    aggregated: List[Dict[str, Any]] = []
    seen_places: set[str] = set()
    overall_limit = int(CONTROLS.get("area_insights_overall_max", 500))

    if CONTROLS.get("area_log_summary"):
        print(f"[AreaInsights][GatherAll] Start types={included_types} max_per={max_per} overall_limit={overall_limit}")

    for t in included_types:
        # Count per single type
        count_data = _area_count_for_types(values, location_filter, [t], operating_status)
        if "_error" in count_data:
            err = count_data["_error"]
            print(f"[AreaInsights][Count][Error] status={err['status']} body={err['body']}")
            continue
        count_val = _parse_count_value(count_data)
        if CONTROLS.get("area_log_summary"):
            print(f"[AreaInsights][Count] types={[t]} count={count_val}")

        if count_val == 0:
            continue

        if count_val <= max_per:
            data = _area_places_for_types(values, location_filter, [t], operating_status)
            if "_error" in data:
                err = data["_error"]
                print(f"[AreaInsights][Places][Error] status={err['status']} body={err['body']}")
                continue
            places = data.get("placeInsights") or []
            added_here = 0
            for pi in places:
                place_resource = pi.get("place")
                if not place_resource:
                    continue
                if place_resource in seen_places:
                    continue
                seen_places.add(place_resource)
                aggregated.append(pi)
                added_here += 1
                if len(aggregated) >= overall_limit:
                    break
            if CONTROLS.get("area_log_summary"):
                print(f"[AreaInsights][Places] returned={len(places)} for types={[t]} added={added_here} total={len(aggregated)}")
            if len(aggregated) >= overall_limit:
                if CONTROLS.get("area_log_summary"):
                    print(f"[AreaInsights][GatherAll] Reached overall limit {overall_limit}; stopping")
                break
        else:
            if CONTROLS.get("area_log_summary"):
                print(f"[AreaInsights][Count] single type {t} exceeds {max_per}; skipping fetch")

    if CONTROLS.get("area_log_summary"):
        print(f"[AreaInsights][GatherAll] Finished total={len(aggregated)} unique places")
    return aggregated


def map_place_to_row(place: Dict[str, Any], keyword: str | None, grid_lat: float | None, grid_lng: float | None) -> List[Any]:
    loc = (place.get("location") or {})
    lat = loc.get("latitude")
    lng = loc.get("longitude")
    display_name = place.get("displayName") or {}
    name_text = display_name.get("text") if isinstance(display_name, dict) else display_name
    types = place.get("types") or []
    return [
        (place.get("id") or place.get("name")),
        name_text,
        place.get("businessStatus"),
        place.get("formattedAddress"),
        lat,
        lng,
        ",".join(types),
        place.get("rating"),
        place.get("userRatingCount"),
        keyword or "",
        grid_lat,
        grid_lng,
    ]


def select_matching_keywords(place_types: List[str], allowed_types: List[str]) -> str:
    if not place_types or not allowed_types:
        return ""
    allowed_set = set(allowed_types)
    ordered_matches: List[str] = []
    for t in place_types:
        if t in allowed_set:
            ordered_matches.append(t)
    return ",".join(ordered_matches)


def shuffled_types(types: List[str], controls: Dict[str, Any]) -> List[str]:
    """Return a shuffled copy of types based on a deterministic seed.

    - Default seed mode is daily: stable per (city_name, UTC date)
    - 'fixed' mode uses a provided integer seed
    - 'random' mode uses a non-deterministic seed each run
    """
    if not types:
        return []
    if not controls.get("area_shuffle_types_enable", False):
        return list(types)

    mode = controls.get("area_shuffle_types_seed_mode", "daily")
    seed_value: int
    if mode == "fixed":
        try:
            seed_value = int(controls.get("area_shuffle_types_fixed_seed") or 0)
        except Exception:
            seed_value = 0
    elif mode == "random":
        seed_bytes = os.urandom(8)
        seed_value = int.from_bytes(seed_bytes, byteorder="big", signed=False)
    else:  # daily
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        city = controls.get("city_name", "") or ""
        key = f"{city}|{today}"
        digest = hashlib.md5(key.encode("utf-8")).digest()
        seed_value = int.from_bytes(digest[:8], byteorder="big", signed=False)

    rng = random.Random(seed_value)
    out = list(types)
    rng.shuffle(out)
    if controls.get("area_log_summary"):
        print(f"[AreaInsights][Types] Shuffled order={out}")
    return out


def extract_place_id(place: Dict[str, Any]) -> str | None:
    return place.get("id") or place.get("name")


def dummy_row() -> list:
    return [
        "test_place_001",
        "Test Café",
        "OPERATIONAL",
        "123 Test St, Chattanooga, TN",
        35.0456,
        -85.3097,
        "cafe,food,point_of_interest,establishment",
        4.5,
        12,
        '"suspended businesses scan"',
        35.05,
        -85.31,
    ]


# Deprecated stubs (kept for backward compatibility)
def places_search_nearby_v1(*args, **kwargs):
    print("[DEPRECATED] places_search_nearby_v1 is removed.")
    return []


def places_search_text_v1(*args, **kwargs):
    print("[DEPRECATED] places_search_text_v1 is removed.")
    return []


def generate_grid_centers(*args, **kwargs):
    print("[DEPRECATED] generate_grid_centers is removed.")
    return []


def places_search_text_chunked(*args, **kwargs):
    print("[DEPRECATED] places_search_text_chunked is removed.")
    return []


def filter_suspended(*args, **kwargs):
    print("[DEPRECATED] filter_suspended is removed.")
    return []


def run_test_places_suspended(*args, **kwargs) -> None:
    print("[DEPRECATED] run_test_places_suspended is removed.")
    return


