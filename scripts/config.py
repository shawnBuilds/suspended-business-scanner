from typing import Any, Dict


# Controls for toggling tests and defaults
CONTROLS: Dict[str, Any] = {
    # High-level city selector (change this only to switch cities)
    "city_name": "Chattanooga",
    "raw_tab_default": "Chattanooga_Raw",
    # Places-related simple controls kept for keyword/type labeling
    "places_radius_m": 50000,
    "places_keyword": "cafe",
    "places_type": None,
    # Granular logging toggles (Area Insights only)
    "enable_verbose_logging": False,
    # Area Insights (computeInsights) controls
    "area_insights_enable": True,
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
    # Logging for Area Insights
    "area_log_request_build": False,
    "area_log_request_send": False,
    "area_log_response_keys": True,
    "area_log_full_response": False,
    "area_log_summary": True,
    "area_log_details_sample_count": 5,  # print N sample details after fetch
    # Area Insights details fetch pacing and caps
    "area_insights_overall_max": 500,
    "area_details_pause_secs": 0.1,
    # Area Insights partitioning
    "area_max_places_per_request": 100,
    "area_skip_large_single_type": True,
    # Writing controls
    "area_insights_write_enabled": True,
    "area_write_only_closed": True,
    # Cities runner controls
    "cities_run_all": False,  # when True, loop all cities in CITY_PRESETS and write per *_Raw tab
    "cities_list": ["Chattanooga", "Medellin", "Santa Cruz"],
}


# City presets: center coordinates and default _Raw tab per city
CITY_PRESETS: Dict[str, Dict[str, Any]] = {
    "Chattanooga": {"lat": 35.0456, "lng": -85.3097, "tab": "Chattanooga_Raw"},
    "Medellin": {"lat": 6.2442, "lng": -75.5812, "tab": "Medellin_Raw"},
    "Santa Cruz": {"lat": 36.9741, "lng": -122.0308, "tab": "SantaCruz_Raw"},
}


