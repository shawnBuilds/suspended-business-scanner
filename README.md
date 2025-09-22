# Suspended Business Scanner

## What it does
- Pulls closed/suspended places via Google Places **Area Insights** → expands with Places **Details** → writes to city `*_Raw` tabs in the shared Sheet.
- Sends a weekly email summary with counts + link to the Sheet.

## How to configure
- Secrets (GitHub Actions): PLACES_API_KEY, SPREADSHEET_ID, SENDGRID_API_KEY, FROM_EMAIL, and service account fields (TYPE, PROJECT_ID, PRIVATE_KEY_ID, PRIVATE_KEY with \n, CLIENT_EMAIL, CLIENT_ID, AUTH_URI, TOKEN_URI, AUTH_PROVIDER_X509_CERT_URL, CLIENT_X509_CERT_URL, UNIVERSE_DOMAIN).
- Recipients: edit the **Config_Recipients** tab (columns: `name, email_address, whatsapp_number`).

## Run locally
- Create `.env` with the same keys as secrets.
- `pip install -r requirements.txt`
- `python scripts/sbs_cli.py`

## Scheduler (GitHub Actions)
- Weekly: Mondays **04:00 UTC** (12:00 AM EDT).
- Change in `.github/workflows/weekly-scan.yml` → `on.schedule.cron`.
- Manual run: GitHub → Actions → “Weekly Suspended Business Scan” → Run workflow.

## Tabs & writing
- Writes only to `*_Raw` tabs (e.g., `Chattanooga_Raw`). View tabs read from Raw.
- Headers expected: `place_id, name, business_status, business_address, lat, lng, types, rating, user_ratings_total, keyword, grid_lat, grid_lng`.

## Alerts
- Email (SendGrid): summary per city + Sheet link (uses `FROM_EMAIL`).
