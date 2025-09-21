### Data snapshots

This folder stores weekly CSV snapshots generated before writing to Google Sheets.

- Naming: `CITY_snapshot_YYYY-Www.csv` (e.g., `Chattanooga_snapshot_2025-W38.csv`)
- Controlled via `scripts/config.py` `CONTROLS`:
  - `snapshot_enable`: enable/disable snapshot writes
  - `snapshot_include_headers`: include headers row in CSV
  - `snapshot_base_dir`: project root for the `data/` folder

An example file is included: `Chattanooga_snapshot_EXAMPLE.csv`.
