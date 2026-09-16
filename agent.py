"""
ToolScout — Core research agent.

Uses Claude claude-sonnet-4-6 with Anthropic's native web_search tool to research
each app and return a structured AppResearch result.

Tier logic:
  Tier 1 — handled by composio_tier.py (skipped here)
  Tier 2 — web_search queries: auth, pricing, MCP
  Tier 3 — deep_fetch triggered if Tier 2 confidence is low/medium on key fields
"""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic
from pydantic import ValidationError
from rich.console import Console

from schema import AppResearch

console = Console()

# ---------------------------------------------------------------------------
# ToolScout system prompt — used verbatim as specified
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are ToolScout, a technical research agent built for Composio — a platform that "
    "turns apps into AI agent toolkits. For each app given, search for its API documentation, "
    "auth method, pricing/access model, and whether an MCP server exists. "
    "\n\n"
    "Return ONLY valid JSON matching the schema provided. Be honest about confidence. "
    "If a page is gated, if docs are thin, or if the app has no public API — say so clearly. "
    "That is a valid and useful finding, not a failure. "
    "\n\n"
    "Rate your own confidence (high/medium/low) on every field. Low confidence fields "
    "are flagged for human verification."
)

# ---------------------------------------------------------------------------
# Per-app user prompt template
# ---------------------------------------------------------------------------
_USER_PROMPT_TEMPLATE = """\
Research this app for Composio's integration pipeline:
App: {app_name}
Website hint: {hint}
Category: {category}

Find and return JSON with all schema fields. Search for:
1. API docs and auth method
2. Whether a developer can self-serve (free/trial) or needs paid plan/sales contact
3. API breadth (how many endpoints/resources)
4. Any existing MCP server (check smithery.ai, npmjs.com, GitHub for "{app_name} MCP server")
5. Primary evidence URL

JSON Schema to follow exactly:
{schema}

Return ONLY the JSON object. No explanation outside the JSON.
"""

_VERIFY_PROMPT_TEMPLATE = """\
You previously researched {app_name}. Here was your answer:
{previous_json}

Search again independently and verify each of these key fields:
- auth_methods
- self_serve
- buildability
- mcp_exists

Return the same full JSON schema with any corrections. Add a brief note in research_notes \
(you may add this as a key called "verification_notes") explaining what changed and why, \
or "no changes" if everything was confirmed.

Return ONLY the JSON object.
"""


def _get_schema_str() -> str:
    """Return a concise JSON Schema string for AppResearch."""
    schema = AppResearch.model_json_schema()
    return json.dumps(schema, indent=2)


def _parse_json_from_response(text: str) -> dict[str, Any]:
    """Extract JSON from model output, handling markdown code fences."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first line (```json or ```) and last line (```)
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).strip()
    return json.loads(text)


def research_app(
    app: dict[str, Any],
    client: anthropic.Anthropic,
    tier: int = 2,
    max_continuations: int = 4,
    previous_result: dict | None = None,
) -> dict[str, Any]:
    """
    Research a single app using ToolScout (Tier 2 web_search or Tier 3 deep_fetch).

    Args:
        app: dict with keys app, category, hint
        client: Anthropic client
        tier: 2 for normal research, 3 for deep verification
        max_continuations: max pause_turn continuations for server-side tools
        previous_result: if set, runs the verification prompt (Pass 2)

    Returns:
        Raw dict conforming to AppResearch schema (not yet validated).
    """
    app_name: str = app["app"]
    hint: str = app.get("hint", "")
    category: str = app.get("category", "")

    # Build user message
    if previous_result is not None:
        user_content = _VERIFY_PROMPT_TEMPLATE.format(
            app_name=app_name,
            previous_json=json.dumps(previous_result, indent=2),
        )
    else:
        user_content = _USER_PROMPT_TEMPLATE.format(
            app_name=app_name,
            hint=hint,
            category=category,
            schema=_get_schema_str(),
        )

    messages: list[dict] = [{"role": "user", "content": user_content}]

    # Use web_search_20250305 as specified
    tools = [{"type": "web_search_20250305", "name": "web_search"}]

    # System prompt cached — stable across all 100 apps
    system_blocks = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    source = "web_search" if tier == 2 else "deep_fetch"
    continuations = 0

    while continuations < max_continuations:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_blocks,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "pause_turn":
            # Server-side tool hit iteration limit — append and continue
            messages.append({"role": "assistant", "content": response.content})
            continuations += 1
            continue

        # Extract the final text block
        text = next(
            (b.text for b in response.content if b.type == "text"),
            None,
        )
        if not text:
            raise ValueError(f"ToolScout got no text output for {app_name}")

        # Parse JSON
        raw = _parse_json_from_response(text)

        # Inject metadata that the model may not set correctly
        raw["app_name"] = app_name
        raw["category"] = category
        raw.setdefault("source", source)
        raw.setdefault("tier_used", tier)

        # Validate with Pydantic (raises on schema mismatch)
        try:
            validated = AppResearch.model_validate(raw)
            return validated.model_dump()
        except ValidationError as exc:
            # Return raw dict with a note — better than crashing
            console.print(
                f"  [yellow]⚠[/yellow]  {app_name}: schema validation warning — {exc.error_count()} field(s)"
            )
            raw.setdefault("run_timestamp", "")
            raw.setdefault("confidence_per_field", {})
            return raw

    raise RuntimeError(
        f"ToolScout: {app_name} exceeded {max_continuations} continuations"
    )
