## Goal

After each scheduled run, send a short summary + Sheet link via email and WhatsApp. Recipients are managed in the Google Sheet (no code changes needed when people change).

## Recipient source (in Google Sheet)

- Create a tab: `Config_Recipients`
- Columns (row 1 headers):
  - `name`
  - `email_address`
  - `whatsapp_number` (E.164 format, e.g., `+14155550123`)
- Add or remove recipients by editing this tab. No redeploy needed.

## Scheduler behavior (high level)

1) Run scans for all configured cities.
2) Compute “new this week” counts per city.
3) Build a single summary message (see template below).
4) Read recipients from `Config_Recipients`.
5) Send the message by Email and WhatsApp.
6) Log success/failure per recipient in workflow logs.

## Message template

- Subject (email): `New suspended businesses this week`
- Body (email & WhatsApp):

  Hey team,

  Here’s how many new businesses we’ve found in each city:

  - {new_chatt} in Chattanooga
  - {new_medellin} in Medellín
  - {new_santacruz} in Santa Cruz

  Check out the details in this sheet: {sheet_link}

  (If zero new anywhere, still send: “No new closures”.)

## Email (SendGrid)

- Use a transactional email service (simpler on Actions than Gmail OAuth).
- Suggested: SendGrid (free tier is enough). Alternatives: Mailgun, AWS SES.
- Create an API key, add repository secret: `SENDGRID_API_KEY`.
- Add `FROM_EMAIL` secret (e.g., `no-reply@yourdomain` or your own email).
- Send one email to all recipients (To list or BCC list).

## WhatsApp (Twilio)

- MVP/dev: Twilio WhatsApp Sandbox
  - Quick to start; each recipient must join the sandbox once (via Twilio-provided code in the console).
  - Required secrets: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` (e.g., `whatsapp:+14155238886`).
- Production: Twilio WhatsApp Business (or WhatsApp Cloud API by Meta)
  - Requires a WhatsApp Business number and approved message templates.
  - Swap credentials but keep the same send interface in code.

## GitHub Actions secrets to add

- Already present: `PLACES_API_KEY`, service-account pieces, `SPREADSHEET_ID`.
- Email:
  - `SENDGRID_API_KEY`
  - `FROM_EMAIL`
- WhatsApp (Twilio):
  - `TWILIO_ACCOUNT_SID`
  - `TWILIO_AUTH_TOKEN`
  - `TWILIO_WHATSAPP_FROM`

## Implementation steps (code)

1) Add recipient reader
   - In `scripts/sheets.py`, add `get_recipients(sh, tab_name="Config_Recipients") -> List[dict]` returning dicts with `name`, `email_address`, `whatsapp_number` (skip blank/incomplete rows).

2) Track when rows are added (to compute “new this week”)
   - Add a new column to appended rows: `added_at_utc` (ISO 8601, e.g., `2025-09-21T07:42:00Z`).
   - Update `required_headers()` in `scripts/sheets.py` and the row mapping in `scripts/helpers.py` so the timestamp is appended for new writes.
   - For existing rows without timestamps, treat them as “not new this week”.

3) Compute weekly new counts per city
   - Add `compute_new_this_week_counts(client) -> Dict[str,int]` that:
     - Opens the spreadsheet via `SPREADSHEET_ID`.
     - For each city’s `*_Raw` tab (from `CITY_PRESETS`), counts rows with `added_at_utc` within the current ISO week (UTC).
     - Returns counts keyed by city name.

4) Build message text
   - Add `build_summary_message(counts: Dict[str,int], sheet_link: str) -> (subject, text)` that renders the template above.

5) Email + WhatsApp senders
   - Create `scripts/notify.py`:
     - `send_email_sendgrid(api_key, from_email, to_emails, subject, body_text)`
     - `send_whatsapp_twilio(account_sid, auth_token, from_whatsapp, to_whatsapp_list, body_text)`
   - Both should raise on hard errors and log per-recipient success/failure.

6) Integrate into the runner
   - In `scripts/sbs_cli.py`, after scans complete:
     - Compute counts via step 3.
     - Read recipients via step 1.
     - Build message via step 4.
     - Send Email (if `SENDGRID_API_KEY` present) and WhatsApp (if Twilio secrets present).
     - Always log a concise summary of what was attempted and outcomes.

7) Workflow: include secrets in `.env`
   - Update `.github/workflows/weekly-scan.yml` “Create .env from secrets” step to include:
     - `SENDGRID_API_KEY`, `FROM_EMAIL`
     - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`

## Testing plan

1) Sheet prep
   - Add your email and a WhatsApp test number to `Config_Recipients`.
   - Ensure the service account has edit access to the spreadsheet.

2) Twilio sandbox
   - In the Twilio console, copy the WhatsApp sandbox join instructions.
   - Each test recipient must join the sandbox once (send the code to the Twilio sandbox number).

3) Dry-run content
   - Leave `area_insights_write_enabled=True` to generate real appends (includes `added_at_utc`).
   - Or add a temporary control `notify_send_even_if_zero=True` to force-send the summary even when counts are zero (for end-to-end notification testing).

4) Trigger runs
   - Use Actions → “Weekly Suspended Business Scan” → Run workflow for immediate testing.
   - Or set cron to every 5 minutes during testing: `*/5 * * * *` (UTC) and push; allow ~5–10 minutes for triggers.

5) Verify
   - Email arrives from `FROM_EMAIL` with the summary.
   - WhatsApp message received from `TWILIO_WHATSAPP_FROM`.
   - Sheet tabs updated with new rows and `added_at_utc` populated.

## Notes

- Keep recipients in the sheet to avoid code changes for stakeholder updates.
- For production WhatsApp, migrate from Sandbox to Business (Meta approval and templates). Reuse the same `notify.py` interface and swap credentials.
- All timestamps and weekly computations should use UTC to align with GitHub Actions cron.
