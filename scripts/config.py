from typing import Any, Dict


# Controls for toggling tests and defaults (ordered for readability)
CONTROLS: Dict[str, Any] = {
    # === High-priority gates (main switches) ===
    # Enable Area Insights (computeInsights) end-to-end
    "area_insights_enable": False,
    # Run all configured cities vs a single city preset
    "cities_run_all": False,
    # Send a test summary email without requiring a full scan
    "notify_email_test_enable": False,

    # === City selection & runner scope ===
    # High-level city selector (change this only to switch cities)
    "city_name": "Medellin",
    "raw_tab_default": "Medellin_Raw",
    # List of cities used when cities_run_all=True
    "cities_list": ["Chattanooga", "Medellin", "Santa Cruz"],

    # === Logging toggles ===
    "enable_verbose_logging": False,
    "area_log_request_build": False,
    "area_log_request_send": False,
    "area_log_response_keys": True,
    "area_log_full_response": False,
    "area_log_summary": True,
    "area_log_details_sample_count": 5,  # print N sample details after fetch

    # === Area Insights (computeInsights) settings ===
    "area_insights_mode": "places",  # "count" or "places"
    "area_insights_location_mode": "circle",  # "circle" | "region" | "customArea"
    "area_insights_circle_radius_m": 40234,
    # Optional list of types, e.g., ["restaurant", "cafe"]
    "area_insights_types": [
        "restaurant",
        "cafe",
        "bakery",
        "bar",
        "coffee_shop",
        "meal_takeaway",
        "meal_delivery",
        "grocery_store",
        "convenience_store",
        "liquor_store",
        "pharmacy",
        "gas_station",
        "gym",
        "hardware_store",
        "electronics_store",
        "clothing_store",
        "department_store",
        "book_store",
        "home_goods_store",
        "furniture_store",
        "lodging",
    ],
    # Default to closures for places mode; for count mode we iterate statuses
    "area_insights_operating_status": [
        "OPERATING_STATUS_TEMPORARILY_CLOSED",
    ],
    # Pacing and caps
    "area_insights_overall_max": 500,
    "area_details_pause_secs": 0.1,
    # Partitioning / reductions
    "area_max_places_per_request": 100,
    "area_skip_large_single_type": True,
    # Fallback: when a single type still exceeds the cap, try the next types
    # If enabled, the runner will iterate over each type individually and fetch
    # from the first type whose count <= cap. If none fit, it will skip.
    "area_enable_single_type_fallback": True,
    # Shuffle types to vary results across runs
    # - area_shuffle_types_enable: master toggle
    # - area_shuffle_types_seed_mode: "daily" | "fixed" | "random"
    #     * daily: deterministic per (city, UTC date)
    #     * fixed: use area_shuffle_types_fixed_seed
    #     * random: non-deterministic each run
    # - area_shuffle_types_fixed_seed: integer seed used when seed_mode == "fixed"
    "area_shuffle_types_enable": True,
    "area_shuffle_types_seed_mode": "daily",
    "area_shuffle_types_fixed_seed": 12345,

    # === Writing & snapshots ===
    "area_insights_write_enabled": True,
    "area_write_only_closed": True,
    # Snapshot controls
    "snapshot_enable": True,  # when True, write CSV snapshot before each city write
    "snapshot_include_headers": True,  # include headers row in snapshot CSV
    "snapshot_base_dir": ".",  # base directory for the 'data' folder

    # === Places (legacy labeling aids) ===
    # Simple controls retained for keyword/type labeling in rows
    "places_radius_m": 50000,
    "places_keyword": "cafe",
    "places_type": None,

    # === Notifications (email test only) ===
    # Optional explicit recipients for test; if empty, will read from 'Recipients' sheet
    "notify_email_test_to_emails": [],
    # Dummy counts for test email when not computing real ones yet
    "notify_email_test_counts": {
        "Chattanooga": 0,
        "Medellin": 0,
        "Santa Cruz": 0,
    },
}


# City presets: center coordinates and default _Raw tab per city
CITY_PRESETS: Dict[str, Dict[str, Any]] = {
    "Chattanooga": {"lat": 35.0456, "lng": -85.3097, "tab": "Chattanooga_Raw"},
    "Medellin": {"lat": 6.2442, "lng": -75.5812, "tab": "Medellin_Raw"},
    "Santa Cruz": {"lat": 36.9741, "lng": -122.0308, "tab": "SantaCruz_Raw"},
}


