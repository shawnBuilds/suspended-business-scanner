from typing import Any, Dict, List

import csv
import os
from datetime import datetime


def _ensure_data_dir(base_dir: str | None = None) -> str:
    target = os.path.join(base_dir or ".", "data")
    os.makedirs(target, exist_ok=True)
    return target


def _iso_week_stamp(dt: datetime | None = None) -> str:
    d = dt or datetime.utcnow()
    year, week_num, _ = d.isocalendar()
    return f"{year}-W{week_num:02d}"


def save_city_snapshot(
    city_name: str,
    rows: List[List[Any]],
    headers: List[str] | None = None,
    base_dir: str | None = None,
) -> str:
    """
    Save a CSV snapshot into ./data named like 'Chattanooga_snapshot_2025-W38.csv'.

    - city_name: Used to prefix the filename
    - rows: 2D list matching headers order
    - headers: optional; written as first row when provided
    - base_dir: optional project root (defaults to '.')

    Returns the absolute path of the written CSV.
    """
    data_dir = _ensure_data_dir(base_dir)
    stamp = _iso_week_stamp()
    safe_city = "".join(c for c in city_name if c.isalnum() or c in ("_", "-", " ")).strip().replace(" ", "_")
    filename = f"{safe_city}_snapshot_{stamp}.csv"
    path = os.path.join(data_dir, filename)

    # If file already exists this week, overwrite to represent the latest pre-write snapshot
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if headers:
            writer.writerow(headers)
        for r in rows:
            writer.writerow(r)
    return os.path.abspath(path)


