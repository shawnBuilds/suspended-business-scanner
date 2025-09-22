import os
import json
import sys
from typing import List, Dict, Tuple

import requests


def load_templates(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Email][Templates] Failed to load {path}: {e}", file=sys.stderr)
        return {}


def render_text(template: str, **kwargs) -> str:
    try:
        return template.format(**kwargs)
    except KeyError as e:
        missing = str(e)
        print(f"[Email][Templates] Missing placeholder: {missing}", file=sys.stderr)
        return template


def send_email_sendgrid(api_key: str,
                        from_email: str,
                        to_emails: List[str],
                        subject: str,
                        body_text: str,
                        from_name: str | None = None) -> None:
    if not api_key:
        raise ValueError("SENDGRID_API_KEY is required")
    if not from_email:
        raise ValueError("FROM_EMAIL is required")
    if not to_emails:
        raise ValueError("At least one recipient is required")

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    sender = {"email": from_email}
    if from_name:
        sender["name"] = from_name

    # One personalization with all recipients in the To list.
    # Adjust to BCC if you prefer hiding recipients from each other.
    body = {
        "personalizations": [
            {
                "to": [{"email": e} for e in to_emails],
                "subject": subject,
            }
        ],
        "from": sender,
        "content": [
            {"type": "text/plain", "value": body_text}
        ],
    }

    resp = requests.post(url, headers=headers, json=body, timeout=30)
    if resp.status_code not in (200, 202):
        try:
            err = resp.json()
        except Exception:
            err = {"non_json": resp.text}
        raise RuntimeError(f"[Email] SendGrid error {resp.status_code}: {err}")


def build_summary_email_message(counts: Dict[str, int],
                                sheet_link: str,
                                templates: dict | None = None,
                                templates_path: str | None = None) -> Tuple[str, str, str | None]:
    """Return (subject, body_text, from_name) for the weekly summary email.

    - counts keys expected: 'Chattanooga', 'Medellin', 'Santa Cruz' (missing default to 0)
    - sheet_link: URL to the Google Sheet
    - templates: optional loaded templates dict
    - templates_path: optional path to templates.json (used if templates is None)
    """
    if templates is None:
        if templates_path is None:
            templates_path = os.path.join(os.path.dirname(__file__), "templates.json")
        templates = load_templates(templates_path)
    email_tpl = (templates.get("email") or {})
    subject = email_tpl.get("subject", "New suspended businesses this week")
    from_name = email_tpl.get("from_name")
    body_template = email_tpl.get(
        "body_text",
        "Hey team,\n\nHere’s how many new businesses we’ve found in each city:\n\n"
        "- {new_chatt} in Chattanooga\n- {new_medellin} in Medellín\n- {new_santacruz} in Santa Cruz\n\n"
        "Check out the details in this sheet: {sheet_link}\n\n(If zero new anywhere, still send: No new closures)",
    )
    body_text = render_text(
        body_template,
        new_chatt=str(counts.get("Chattanooga", 0)),
        new_medellin=str(counts.get("Medellin", 0)),
        new_santacruz=str(counts.get("Santa Cruz", 0)),
        sheet_link=sheet_link,
    )
    return subject, body_text, from_name


def send_weekly_summary_email(api_key: str,
                              from_email: str,
                              to_emails: List[str],
                              counts: Dict[str, int],
                              sheet_link: str,
                              templates: dict | None = None,
                              templates_path: str | None = None) -> None:
    """Convenience wrapper: build the summary message and send via SendGrid."""
    subject, body_text, from_name = build_summary_email_message(
        counts=counts,
        sheet_link=sheet_link,
        templates=templates,
        templates_path=templates_path,
    )
    send_email_sendgrid(
        api_key=api_key,
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        body_text=body_text,
        from_name=from_name,
    )


 


