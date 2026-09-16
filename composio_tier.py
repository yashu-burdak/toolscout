"""
ToolScout — Tier 1: Composio native integration check.

Checks whether an app already exists on Composio's integration list.
Apps found here get source='composio_native', confidence='high', tier_used=1.
These ~40 apps are ground truth — the agent does not re-research them.
"""

from __future__ import annotations

import os
import json
import re
from pathlib import Path

from rich.console import Console

console = Console()

# ---------------------------------------------------------------------------
# Known Composio integrations (fetched / maintained manually as fallback)
# These are the integrations listed on app.composio.dev/apps as of the run.
# The SDK call below attempts a live fetch; this list is the fallback.
# ---------------------------------------------------------------------------
_KNOWN_COMPOSIO_APPS: set[str] = {
    "github", "gitlab", "notion", "slack", "jira", "asana", "linear",
    "trello", "monday.com", "clickup", "airtable", "hubspot", "salesforce",
    "pipedrive", "zendesk", "intercom", "freshdesk", "gmail", "google calendar",
    "google drive", "google sheets", "google docs", "dropbox", "box",
    "stripe", "shopify", "twilio", "sendgrid", "mailchimp", "klaviyo",
    "discord", "telegram", "whatsapp business", "zoom", "microsoft teams",
    "figma", "canva", "webflow", "wordpress", "squarespace", "woocommerce",
    "quickbooks", "xero", "snowflake", "mongodb atlas", "supabase",
    "datadog", "sentry", "vercel", "netlify", "cloudflare", "aws",
    "google ads", "meta ads", "linkedin", "twitter", "pinterest",
    "harvest", "toggl", "calendly", "typeform", "surveymonkey",
    "close", "copper", "podio", "zoho crm", "attio",
    "front", "help scout", "gorgias", "aircall",
    "apify", "firecrawl", "bright data",
    "brex", "ramp", "plaid",
    "devin",
}


def _normalize(name: str) -> str:
    """Lowercase + strip punctuation for fuzzy matching."""
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def _live_composio_apps() -> set[str] | None:
    """
    Attempt to fetch the live Composio integration list via the SDK.
    Returns a set of lowercased app names, or None if the SDK is unavailable.
    """
    try:
        from composio_anthropic import ComposioToolSet  # type: ignore

        toolset = ComposioToolSet(api_key=os.getenv("COMPOSIO_API_KEY"))
        apps = toolset.get_apps()  # returns list of App objects
        names: set[str] = set()
        for app in apps:
            # ComposioToolSet.get_apps() returns App objects with .name
            raw = getattr(app, "name", None) or str(app)
            names.add(_normalize(raw))
        console.print(
            f"[dim]ToolScout Tier 1: fetched {len(names)} Composio integrations live[/dim]"
        )
        return names
    except Exception as exc:
        console.print(
            f"[dim]ToolScout Tier 1: Composio SDK unavailable ({exc}), "
            "using static fallback list[/dim]"
        )
        return None


# Cache the live list once per process
_LIVE_APPS: set[str] | None = None
_LIVE_FETCHED = False


def _get_composio_apps() -> set[str]:
    global _LIVE_APPS, _LIVE_FETCHED
    if not _LIVE_FETCHED:
        _LIVE_APPS = _live_composio_apps()
        _LIVE_FETCHED = True
    if _LIVE_APPS is not None:
        return _LIVE_APPS
    return {_normalize(a) for a in _KNOWN_COMPOSIO_APPS}


def is_composio_native(app_name: str) -> bool:
    """Return True if this app is already in Composio's integration catalog."""
    needle = _normalize(app_name)
    apps = _get_composio_apps()
    # Exact match
    if needle in apps:
        return True
    # Prefix / substring match for composite names (e.g. "Zoho CRM" → "zoho crm")
    for known in apps:
        if needle in known or known in needle:
            return True
    return False


def get_composio_stub(app: dict) -> dict:
    """
    Return a pre-filled research stub for a Composio-native app.
    Marked source='composio_native', tier_used=1, confidence='high'.

    Fields that Composio's presence confirms:
      - self_serve: True  (Composio only integrates apps with accessible APIs)
      - buildability: 'ready'
      - opportunity_score: ≥ 3 (already integrated = demand proven)

    Fields left for the agent to fill if desired (we set reasonable defaults):
      - auth_methods, api_type, api_breadth, mcp_exists, etc.
    """
    from datetime import datetime

    name = app["app"]
    return {
        "app_name": name,
        "category": app["category"],
        "one_liner": f"{name} — already on Composio's integration catalog.",
        "auth_methods": ["OAuth2"],           # most Composio integrations use OAuth2
        "self_serve": True,
        "trial_available": True,
        "gating_note": "Available as Composio integration — self-serve via Composio SDK",
        "api_type": "REST",
        "api_breadth": "broad",
        "mcp_exists": False,
        "mcp_url": None,
        "buildability": "ready",
        "blocker": None,
        "opportunity_score": 4,
        "evidence_url": f"https://app.composio.dev/apps",
        "confidence": "high",
        "confidence_per_field": {
            "auth_methods": "medium",
            "self_serve": "high",
            "api_breadth": "high",
            "mcp_exists": "medium",
            "buildability": "high",
        },
        "source": "composio_native",
        "tier_used": 1,
        "run_timestamp": datetime.utcnow().isoformat(),
    }
