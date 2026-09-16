"""
ToolScout — Main entrypoint.

Execution order:
  1. Write hardcoded edge-case stubs to data/raw/
  2. Run pre-validation on 5 anchor apps — stop for human confirmation
  3. Check each app against Tier 1 (Composio native)
  4. Run ToolScout agent (Tier 2/3) for remaining apps in batches of 10
  5. Merge raw/ + verified/ → data/final.json

Resume support: if data/raw/{app}.json already exists, skip that app.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import openai
from dotenv import dotenv_values
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent import research_app
from composio_tier import get_composio_stub, is_composio_native

# Load .env explicitly and inject into os.environ
_env = dotenv_values(Path(__file__).parent / ".env")
for _k, _v in _env.items():
    if _v is not None:
        os.environ[_k] = _v
console = Console()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
VERIFIED_DIR = DATA_DIR / "verified"
FINAL_PATH = DATA_DIR / "final.json"
PREVALIDATION_PATH = DATA_DIR / "prevalidation.json"
APPS_PATH = DATA_DIR / "apps.json"

RAW_DIR.mkdir(parents=True, exist_ok=True)
VERIFIED_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Hardcoded edge-case stubs (written before any agent run)
# ---------------------------------------------------------------------------
EDGE_CASES: list[dict] = [
    {
        "app_name": "Sherlock",
        "category": "Data SEO and Scraping",
        "one_liner": "CLI tool for hunting usernames across social networks — no public API.",
        "auth_methods": ["None"],
        "self_serve": False,
        "trial_available": False,
        "gating_note": "CLI tool only — no REST API exists",
        "api_type": "None",
        "api_breadth": "none",
        "mcp_exists": False,
        "mcp_url": None,
        "buildability": "non_standard",
        "blocker": "CLI tool only, no REST API surface",
        "opportunity_score": 1,
        "evidence_url": "https://github.com/sherlock-project/sherlock",
        "confidence": "high",
        "confidence_per_field": {
            "auth_methods": "high", "self_serve": "high",
            "api_breadth": "high", "mcp_exists": "high", "buildability": "high",
        },
        "source": "manual",
        "tier_used": 0,
        "run_timestamp": datetime.utcnow().isoformat(),
    },
    {
        "app_name": "Mermaid CLI",
        "category": "AI Research and Media",
        "one_liner": "CLI tool for generating diagrams from text — no HTTP API.",
        "auth_methods": ["None"],
        "self_serve": False,
        "trial_available": False,
        "gating_note": "CLI/npm package only — no REST API exists",
        "api_type": "None",
        "api_breadth": "none",
        "mcp_exists": False,
        "mcp_url": None,
        "buildability": "non_standard",
        "blocker": "CLI tool only, no REST API surface",
        "opportunity_score": 1,
        "evidence_url": "https://github.com/mermaid-js/mermaid-cli",
        "confidence": "high",
        "confidence_per_field": {
            "auth_methods": "high", "self_serve": "high",
            "api_breadth": "high", "mcp_exists": "high", "buildability": "high",
        },
        "source": "manual",
        "tier_used": 0,
        "run_timestamp": datetime.utcnow().isoformat(),
    },
    {
        "app_name": "fanbasis",
        "category": "Ecommerce",
        "one_liner": "Niche e-commerce platform with near-zero public API documentation.",
        "auth_methods": ["Unknown"],
        "self_serve": False,
        "trial_available": False,
        "gating_note": "No publicly documented API found",
        "api_type": "None",
        "api_breadth": "none",
        "mcp_exists": False,
        "mcp_url": None,
        "buildability": "not_buildable",
        "blocker": "No public API documentation",
        "opportunity_score": 1,
        "evidence_url": "https://fanbasis.com",
        "confidence": "high",
        "confidence_per_field": {
            "auth_methods": "high", "self_serve": "high",
            "api_breadth": "high", "mcp_exists": "high", "buildability": "high",
        },
        "source": "manual",
        "tier_used": 0,
        "run_timestamp": datetime.utcnow().isoformat(),
    },
    {
        "app_name": "iPayX",
        "category": "Finance and Fintech",
        "one_liner": "Payment processing service with thin/unclear public API docs.",
        "auth_methods": ["API Key"],
        "self_serve": False,
        "trial_available": False,
        "gating_note": "Docs sparse — likely requires sales outreach for API access",
        "api_type": "REST",
        "api_breadth": "narrow",
        "mcp_exists": False,
        "mcp_url": None,
        "buildability": "needs_outreach",
        "blocker": "Documentation unclear; API access likely requires sales contact",
        "opportunity_score": 2,
        "evidence_url": "https://ipayx.ai",
        "confidence": "low",
        "confidence_per_field": {
            "auth_methods": "low", "self_serve": "low",
            "api_breadth": "low", "mcp_exists": "high", "buildability": "low",
        },
        "source": "manual",
        "tier_used": 0,
        "run_timestamp": datetime.utcnow().isoformat(),
    },
    {
        "app_name": "Paygent Connect",
        "category": "Finance and Fintech",
        "one_liner": "NMI-powered payment gateway with unclear public API access.",
        "auth_methods": ["API Key"],
        "self_serve": False,
        "trial_available": False,
        "gating_note": "NMI-powered reseller — API likely requires partnership/sales",
        "api_type": "REST",
        "api_breadth": "narrow",
        "mcp_exists": False,
        "mcp_url": None,
        "buildability": "needs_outreach",
        "blocker": "NMI-powered reseller; unclear self-serve API access",
        "opportunity_score": 2,
        "evidence_url": "https://nmi.com",
        "confidence": "low",
        "confidence_per_field": {
            "auth_methods": "low", "self_serve": "low",
            "api_breadth": "low", "mcp_exists": "high", "buildability": "low",
        },
        "source": "manual",
        "tier_used": 0,
        "run_timestamp": datetime.utcnow().isoformat(),
    },
    {
        "app_name": "DealCloud",
        "category": "CRM and Sales",
        "one_liner": "Enterprise deal management platform for PE/VC — API requires enterprise contract.",
        "auth_methods": ["OAuth2"],
        "self_serve": False,
        "trial_available": False,
        "gating_note": "Enterprise-only; contact sales required",
        "api_type": "REST",
        "api_breadth": "moderate",
        "mcp_exists": False,
        "mcp_url": None,
        "buildability": "needs_outreach",
        "blocker": "Enterprise contract required — no self-serve access",
        "opportunity_score": 2,
        "evidence_url": "https://intapp.com/products/dealcloud",
        "confidence": "high",
        "confidence_per_field": {
            "auth_methods": "medium", "self_serve": "high",
            "api_breadth": "medium", "mcp_exists": "high", "buildability": "high",
        },
        "source": "manual",
        "tier_used": 0,
        "run_timestamp": datetime.utcnow().isoformat(),
    },
    {
        "app_name": "Gladly",
        "category": "Support and Helpdesk",
        "one_liner": "Enterprise customer service platform — API requires enterprise contract.",
        "auth_methods": ["API Key"],
        "self_serve": False,
        "trial_available": False,
        "gating_note": "Enterprise gated — no self-serve API access",
        "api_type": "REST",
        "api_breadth": "moderate",
        "mcp_exists": False,
        "mcp_url": None,
        "buildability": "needs_outreach",
        "blocker": "Enterprise-only; contact sales for API access",
        "opportunity_score": 2,
        "evidence_url": "https://developer.gladly.com",
        "confidence": "high",
        "confidence_per_field": {
            "auth_methods": "medium", "self_serve": "high",
            "api_breadth": "medium", "mcp_exists": "high", "buildability": "high",
        },
        "source": "manual",
        "tier_used": 0,
        "run_timestamp": datetime.utcnow().isoformat(),
    },
    {
        "app_name": "PitchBook",
        "category": "Finance and Fintech",
        "one_liner": "Financial data platform for PE/VC — API heavily gated behind enterprise plans.",
        "auth_methods": ["API Key"],
        "self_serve": False,
        "trial_available": False,
        "gating_note": "Requires enterprise subscription; API access not self-serve",
        "api_type": "REST",
        "api_breadth": "broad",
        "mcp_exists": False,
        "mcp_url": None,
        "buildability": "needs_outreach",
        "blocker": "Enterprise contract required; no trial or self-serve API tier",
        "opportunity_score": 3,
        "evidence_url": "https://pitchbook.com/about/api-data-feeds",
        "confidence": "high",
        "confidence_per_field": {
            "auth_methods": "high", "self_serve": "high",
            "api_breadth": "medium", "mcp_exists": "high", "buildability": "high",
        },
        "source": "manual",
        "tier_used": 0,
        "run_timestamp": datetime.utcnow().isoformat(),
    },
    {
        "app_name": "NotebookLM",
        "category": "AI Research and Media",
        "one_liner": "Google's AI research tool — no public API as of 2025.",
        "auth_methods": ["None"],
        "self_serve": False,
        "trial_available": False,
        "gating_note": "No public API available; product is UI-only",
        "api_type": "None",
        "api_breadth": "none",
        "mcp_exists": False,
        "mcp_url": None,
        "buildability": "not_buildable",
        "blocker": "No public API — UI-only product",
        "opportunity_score": 1,
        "evidence_url": "https://notebooklm.google.com",
        "confidence": "high",
        "confidence_per_field": {
            "auth_methods": "high", "self_serve": "high",
            "api_breadth": "high", "mcp_exists": "high", "buildability": "high",
        },
        "source": "manual",
        "tier_used": 0,
        "run_timestamp": datetime.utcnow().isoformat(),
    },
    {
        "app_name": "higgsfield",
        "category": "AI Research and Media",
        "one_liner": "AI video generation tool — primarily CLI-based with limited API surface.",
        "auth_methods": ["API Key"],
        "self_serve": False,
        "trial_available": False,
        "gating_note": "CLI/content tool — limited public API; waitlist for API access",
        "api_type": "REST",
        "api_breadth": "narrow",
        "mcp_exists": False,
        "mcp_url": None,
        "buildability": "non_standard",
        "blocker": "CLI-first product; API is limited and access unclear",
        "opportunity_score": 2,
        "evidence_url": "https://higgsfield.ai",
        "confidence": "high",
        "confidence_per_field": {
            "auth_methods": "medium", "self_serve": "high",
            "api_breadth": "medium", "mcp_exists": "high", "buildability": "high",
        },
        "source": "manual",
        "tier_used": 0,
        "run_timestamp": datetime.utcnow().isoformat(),
    },
]

# Pre-validation anchor apps
PREVALIDATION_APPS = ["Stripe", "GitHub", "Notion", "Slack", "Salesforce"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _app_cache_path(app_name: str) -> Path:
    safe = app_name.lower().replace(" ", "_").replace("/", "_")
    return RAW_DIR / f"{safe}.json"


def _load_app(app_name: str) -> dict | None:
    p = _app_cache_path(app_name)
    if p.exists():
        return json.loads(p.read_text())
    return None


def _save_app(result: dict) -> None:
    p = _app_cache_path(result["app_name"])
    p.write_text(json.dumps(result, indent=2))


def _write_edge_cases() -> None:
    """Write all hardcoded edge cases to data/raw/ at startup."""
    for stub in EDGE_CASES:
        path = _app_cache_path(stub["app_name"])
        if not path.exists():
            path.write_text(json.dumps(stub, indent=2))
            console.print(f"  [dim]⚡ Edge case written: {stub['app_name']}[/dim]")


# ---------------------------------------------------------------------------
# Pre-validation
# ---------------------------------------------------------------------------

def run_prevalidation(apps_by_name: dict[str, dict], client: openai.OpenAI) -> None:
    console.print(Panel(
        "[bold indigo]ToolScout Pre-Validation (5 apps)[/bold indigo]\n"
        "Running on: Stripe, GitHub, Notion, Slack, Salesforce",
        border_style="blue",
    ))

    results: list[dict] = []
    for app_name in PREVALIDATION_APPS:
        app = apps_by_name.get(app_name)
        if not app:
            console.print(f"  [red]✗[/red] {app_name} not found in apps.json")
            continue

        console.print(f"  [cyan]🔍[/cyan] Researching {app_name}...")

        # Check Tier 1 first
        if is_composio_native(app_name):
            result = get_composio_stub(app)
            console.print(f"  [green]✓[/green] {app_name} [Tier 1 — Composio Native]")
        else:
            result = research_app(app, client, tier=2)
            console.print(f"  [green]✓[/green] {app_name} [Tier 2 — web_search]")

        results.append(result)
        _save_app(result)

    # Print summary table
    table = Table(title="Pre-Validation Results", show_lines=True)
    table.add_column("App", style="bold")
    table.add_column("Auth")
    table.add_column("Self-Serve")
    table.add_column("Buildability")
    table.add_column("Confidence")
    table.add_column("Score")

    for r in results:
        table.add_row(
            r.get("app_name", "?"),
            ", ".join(r.get("auth_methods", [])),
            "✅" if r.get("self_serve") else "❌",
            r.get("buildability", "?"),
            r.get("confidence", "?"),
            str(r.get("opportunity_score", "?")),
        )
    console.print(table)

    PREVALIDATION_PATH.write_text(json.dumps(results, indent=2))
    console.print(f"[dim]Pre-validation saved to {PREVALIDATION_PATH}[/dim]\n")

    # Human confirmation gate
    console.print("[bold yellow]⚠️  Does the pre-validation look correct?[/bold yellow]")
    console.print("   Check that auth methods, self_serve, and buildability are accurate.")
    answer = input("   Proceed with full 100-app run? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        console.print("[red]Aborted by user.[/red]")
        sys.exit(0)


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def main() -> None:
    console.print(Panel(
        "[bold]🔍 ToolScout[/bold]\n"
        "100-app API research pipeline for Composio\n"
        f"Started: {datetime.utcnow().isoformat()}",
        border_style="blue",
    ))

    # Load app list
    apps: list[dict] = json.loads(APPS_PATH.read_text())
    apps_by_name: dict[str, dict] = {a["app"]: a for a in apps}

    # Step 1: Write edge cases to cache immediately
    console.print("\n[bold]Step 1/4[/bold] Writing edge cases to cache...")
    _write_edge_cases()

    # Step 2: Pre-validation on 5 anchor apps
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[red]OPENAI_API_KEY not set in .env — aborting.[/red]")
        sys.exit(1)
    client = openai.OpenAI(api_key=api_key)
    console.print("\n[bold]Step 2/4[/bold] Pre-validation...")
    run_prevalidation(apps_by_name, client)

    # Step 3: Research all 100 apps
    console.print("\n[bold]Step 3/4[/bold] Researching all 100 apps (batches of 10)...\n")

    done = 0
    errors: list[str] = []

    for batch_start in range(0, len(apps), 10):
        batch = apps[batch_start : batch_start + 10]

        for app in batch:
            app_name: str = app["app"]
            idx = app["id"]

            # Resume: skip if already cached
            if _app_cache_path(app_name).exists():
                console.print(
                    f"  [dim]→ {app_name} ({idx}/100) — cache hit, skipped[/dim]"
                )
                done += 1
                continue

            # Tier 1: Composio native
            if is_composio_native(app_name):
                result = get_composio_stub(app)
                _save_app(result)
                console.print(
                    f"  [green]✓[/green] {app_name} ({idx}/100) [Tier 1 — Composio Native] "
                    f"confidence: {result['confidence']}"
                )
                done += 1
                continue

            # Tier 2/3: agent research
            console.print(
                f"  [cyan]🔍[/cyan] ToolScout researching: {app_name} ({idx}/100) [Tier 2]"
            )
            try:
                result = research_app(app, client, tier=2)

                # Tier 3 escalation: if key fields are low/medium confidence
                key_conf = result.get("confidence_per_field", {})
                low_fields = [
                    f for f, c in key_conf.items()
                    if c in ("low", "medium") and f in ("self_serve", "buildability", "auth_methods")
                ]
                if result.get("confidence") == "low" or len(low_fields) >= 2:
                    console.print(
                        f"  [yellow]↑[/yellow] {app_name} — escalating to Tier 3 (low confidence)"
                    )
                    result = research_app(app, client, tier=3)

                _save_app(result)
                buildability = result.get("buildability", "?")
                confidence = result.get("confidence", "?")
                console.print(
                    f"  [green]✅[/green] {app_name} done — "
                    f"confidence: {confidence}, buildability: {buildability}"
                )
                done += 1

            except Exception as exc:
                errors.append(f"{app_name}: {exc}")
                console.print(f"  [red]✗[/red] {app_name} FAILED: {exc}")

        # Batch delay (2s between batches)
        if batch_start + 10 < len(apps):
            time.sleep(2)

    # Step 4: Merge raw/ + verified/ → final.json
    console.print(f"\n[bold]Step 4/4[/bold] Merging results → {FINAL_PATH}")
    _merge_final()

    console.print(f"\n[bold green]✅ ToolScout complete![/bold green]")
    console.print(f"   {done}/100 apps researched")
    if errors:
        console.print(f"   [red]{len(errors)} errors:[/red]")
        for e in errors:
            console.print(f"     • {e}")
    console.print(f"\n   Next: run [bold]python build_html.py[/bold] to generate index.html")


def _merge_final() -> None:
    """Merge data/raw/ and data/verified/ into data/final.json."""
    merged: dict[str, dict] = {}

    # Load raw results
    for p in sorted(RAW_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            key = data.get("app_name", p.stem)
            merged[key] = data
        except Exception:
            pass

    # Overlay verified corrections (human spot-check)
    for p in sorted(VERIFIED_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            key = data.get("app_name", p.stem)
            merged[key] = data  # verified takes precedence
        except Exception:
            pass

    final = sorted(merged.values(), key=lambda x: x.get("app_name", ""))
    FINAL_PATH.write_text(json.dumps(final, indent=2))
    console.print(f"  [green]✓[/green] {len(final)} apps in final.json")


if __name__ == "__main__":
    main()
