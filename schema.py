"""
ToolScout — Data contract for API research output.
Every field has a description and agent-rated confidence score.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AppResearch(BaseModel):
    # ── Identity ──────────────────────────────────────────────────────────────
    app_name: str = Field(description="Canonical name of the app/service being researched")
    category: str = Field(description="Category from apps.json (e.g. CRM and Sales)")
    one_liner: str = Field(description="What this service does in one concise sentence")

    # ── Authentication ────────────────────────────────────────────────────────
    auth_methods: list[str] = Field(
        description="Authentication methods the API supports. "
                    "Use values from: [OAuth2, API Key, Basic Auth, Bearer Token, Token, Other, None]"
    )

    # ── Access model ──────────────────────────────────────────────────────────
    self_serve: bool = Field(
        description="True if a developer can sign up and get API credentials without contacting sales"
    )
    trial_available: bool = Field(
        description="True if a free tier or trial exists that allows API experimentation"
    )
    gating_note: str = Field(
        description="Short note on access gating, e.g. 'free tier available', "
                    "'contact sales required', 'requires paid plan ($99/mo+)'"
    )

    # ── API surface ───────────────────────────────────────────────────────────
    api_type: str = Field(
        description="Primary API type: REST / GraphQL / Both / gRPC / WebSocket / None"
    )
    api_breadth: str = Field(
        description="How extensive the API is: broad / moderate / narrow / none. "
                    "broad = covers most core resources; narrow = limited endpoints"
    )

    # ── MCP ───────────────────────────────────────────────────────────────────
    mcp_exists: bool = Field(
        description="True if a published MCP server exists for this app "
                    "(check smithery.ai, npm, GitHub, official docs)"
    )
    mcp_url: Optional[str] = Field(
        default=None,
        description="URL of the MCP server package or repository, if it exists"
    )

    # ── Agent buildability ────────────────────────────────────────────────────
    buildability: str = Field(
        description="One of: ready / needs_outreach / not_buildable / non_standard. "
                    "ready = self-serve + decent API; "
                    "needs_outreach = gated but API exists; "
                    "not_buildable = no public API; "
                    "non_standard = CLI/SDK only, no REST API"
    )
    blocker: Optional[str] = Field(
        default=None,
        description="Primary blocker if buildability != 'ready', e.g. 'requires enterprise contract'"
    )

    # ── Opportunity scoring ───────────────────────────────────────────────────
    opportunity_score: int = Field(
        ge=1, le=5,
        description="Composite 1–5 score: API breadth × self_serve × demand signal. "
                    "5 = top build priority for Composio; 1 = skip"
    )

    # ── Evidence & metadata ───────────────────────────────────────────────────
    evidence_url: str = Field(
        description="Primary URL used as evidence (API docs page, pricing page, etc.)"
    )

    # ── Confidence ────────────────────────────────────────────────────────────
    confidence: str = Field(
        description="Agent's overall confidence in this research result: high / medium / low"
    )
    confidence_per_field: dict[str, str] = Field(
        description="Per-field confidence ratings for key fields. "
                    "Keys: auth_methods, self_serve, api_breadth, mcp_exists, buildability. "
                    "Values: high / medium / low"
    )

    # ── Provenance ────────────────────────────────────────────────────────────
    source: str = Field(
        description="How this result was obtained: "
                    "composio_native / web_search / deep_fetch / manual"
    )
    tier_used: int = Field(
        ge=1, le=3,
        description="Which research tier resolved this app: 1 (Composio), 2 (web search), 3 (deep fetch)"
    )
    run_timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO 8601 UTC timestamp when this research was completed"
    )
