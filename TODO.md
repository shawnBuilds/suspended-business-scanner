## Goal

Set up a GitHub Actions scheduler so the scan runs automatically on a weekly schedule (and can also be run on-demand with one click). The workflow should install dependencies, load credentials from secrets into a .env, execute `scripts/sbs_cli.py`, and write results to Google Sheets.

## Prerequisites

- Repository permissions to manage Actions and Secrets.
- Google Cloud service account with Sheets/Drive access to the target spreadsheet.
- The following repository Secrets created (names are suggestions; update if you prefer different names):
  - PLACES_API_KEY
  - SPREADSHEET_ID
  - TYPE (normally `service_account`)
  - PROJECT_ID
  - PRIVATE_KEY_ID
  - PRIVATE_KEY (store with `\n` escaped newlines)
  - CLIENT_EMAIL
  - CLIENT_ID
  - AUTH_URI
  - TOKEN_URI
  - AUTH_PROVIDER_X509_CERT_URL
  - CLIENT_X509_CERT_URL
  - UNIVERSE_DOMAIN (optional; default `googleapis.com`)

Tip: PRIVATE_KEY must be pasted with literal `\n` sequences (not real newlines). The code converts `\n` back to newlines internally.

## Time settings (cron)

- GitHub Actions `schedule` uses cron in UTC.
- Examples:
  - Every Monday at 13:00 UTC: `0 13 * * 1`
  - Every Wednesday at 02:30 UTC: `30 2 * * 3`
  - Hourly during testing: `0 * * * *`
  - Every 15 minutes during testing: `*/15 * * * *`

Note: Schedules are not guaranteed to run at the exact second and can be delayed. Keep that in mind for short test intervals.

## Key functions of the scheduler

- Triggers per cron (`on.schedule`) and on-demand (`workflow_dispatch`).
- Creates a Python environment and installs `requirements.txt`.
- Materializes a `.env` file from Secrets so the code runs without modifications.
- Executes `scripts/sbs_cli.py` with your configured controls (e.g., `cities_run_all`, chosen city/tab).
- Optional: uploads snapshot CSVs from the `data/` directory as build artifacts for auditing.
- Uses concurrency to prevent overlapping runs.

## Implementation steps

1) Create the workflow file

Create `.github/workflows/weekly-scan.yml` with the following content (adjust schedule as needed):

```yaml
name: Weekly Suspended Business Scan

on:
  schedule:
    # Every Monday at 13:00 UTC
    - cron: '0 13 * * 1'
  workflow_dispatch: {}

concurrency:
  group: weekly-scan
  cancel-in-progress: false

jobs:
  run-scan:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Create .env from secrets
        run: |
          {
            echo "PLACES_API_KEY=${{ secrets.PLACES_API_KEY }}";
            echo "SPREADSHEET_ID=${{ secrets.SPREADSHEET_ID }}";
            echo "TYPE=${{ secrets.TYPE }}";
            echo "PROJECT_ID=${{ secrets.PROJECT_ID }}";
            echo "PRIVATE_KEY_ID=${{ secrets.PRIVATE_KEY_ID }}";
            echo "PRIVATE_KEY=${{ secrets.PRIVATE_KEY }}";
            echo "CLIENT_EMAIL=${{ secrets.CLIENT_EMAIL }}";
            echo "CLIENT_ID=${{ secrets.CLIENT_ID }}";
            echo "AUTH_URI=${{ secrets.AUTH_URI }}";
            echo "TOKEN_URI=${{ secrets.TOKEN_URI }}";
            echo "AUTH_PROVIDER_X509_CERT_URL=${{ secrets.AUTH_PROVIDER_X509_CERT_URL }}";
            echo "CLIENT_X509_CERT_URL=${{ secrets.CLIENT_X509_CERT_URL }}";
            echo "UNIVERSE_DOMAIN=${{ secrets.UNIVERSE_DOMAIN }}";
            # Optional override for tab
            if [ -n "${{ secrets.RAW_TAB }}" ]; then echo "RAW_TAB=${{ secrets.RAW_TAB }}"; fi;
          } > .env

      - name: Run scan
        run: |
          python scripts/sbs_cli.py

      - name: Upload snapshot CSVs (optional)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: data-snapshots
          path: |
            data/*.csv
          if-no-files-found: ignore
```

2) Verify controls

- In `scripts/config.py` set the desired city (or enable `cities_run_all`) and ensure `area_insights_enable=True`.
- To limit write impact during testing, you can set `"area_insights_write_enabled": False` temporarily.

3) Add repository secrets

- Populate all required secrets listed in Prerequisites.
- For the PRIVATE_KEY, replace actual newlines with `\n` before saving.

4) Commit and push

- Commit the workflow file to the default branch (usually `main`). Scheduled triggers run against the default branch.

## Testing the scheduler

Option A — Manual runs (recommended for quick tests)
- Open the repository’s Actions tab.
- Select “Weekly Suspended Business Scan”.
- Click “Run workflow” to trigger `workflow_dispatch` any time.

Option B — Short test schedule
- Temporarily change the cron to `*/15 * * * *` (every 15 minutes) and push to the default branch.
- Observe runs for ~30–60 minutes, then restore the weekly cron.

Option C — Dry-run without writing
- Set `"area_insights_write_enabled": False` in `scripts/config.py` to avoid modifying Sheets while verifying logs.
- Alternatively, set `RAW_TAB` as a temporary secret for a test tab.

## Operational notes

- Cron is evaluated in UTC. If you need a specific local time, convert to UTC and consider DST shifts.
- Scheduled jobs can be delayed by several minutes.
- Use `concurrency` to prevent overlapping runs if a prior job is still executing when the next trigger fires.
- Artifacts step is optional but helpful to archive the generated CSV snapshots under `data/` for auditing.


