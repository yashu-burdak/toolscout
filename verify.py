"""
ToolScout — Three-pass verification system.

Pass 1: Confidence-weighted accuracy estimate across all 100 apps.
Pass 2: 20-app re-research sample (biased toward low/medium confidence).
Pass 3: Human check placeholder — outputs apps needing manual review.

Outputs:
  data/verification_report.json
  data/honest_misses.json
  data/needs_human_check.json
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic
from dotenv import dotenv_values
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from agent import research_app
from schema import AppResearch

_env = dotenv_values(Path(__file__).parent / ".env")
for _k, _v in _env.items():
    if _v is not None:
        os.environ[_k] = _v
console = Console()

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
VERIFIED_DIR = DATA_DIR / "verified"

# Confidence → estimated accuracy mapping
CONFIDENCE_ACCURACY = {"high": 0.90, "medium": 0.70, "low": 0.50}

# Key fields compared in Pass 2
COMPARE_FIELDS = ["auth_methods", "self_serve", "buildability", "mcp_exists"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_raw_results() -> list[dict[str, Any]]:
    """Load all per-app JSON files from data/raw/."""
    results: list[dict[str, Any]] = []
    for path in sorted(RAW_DIR.glob("*.json")):
        try:
            results.append(json.loads(path.read_text()))
        except Exception:
            pass
    return results


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _normalize_auth(val: Any) -> frozenset[str]:
    """Normalize auth_methods to a frozenset for comparison."""
    if isinstance(val, list):
        return frozenset(str(v).lower().strip() for v in val)
    return frozenset([str(val).lower().strip()])


def _fields_match(pass1: dict, pass2: dict) -> tuple[bool, list[str]]:
    """
    Compare key fields between two research results.
    Returns (overall_agreed, list_of_mismatching_field_names).
    """
    mismatches: list[str] = []
    for field in COMPARE_FIELDS:
        v1 = pass1.get(field)
        v2 = pass2.get(field)
        if field == "auth_methods":
            if _normalize_auth(v1) != _normalize_auth(v2):
                mismatches.append(field)
        else:
            if v1 != v2:
                mismatches.append(field)
    return (len(mismatches) == 0, mismatches)


# ---------------------------------------------------------------------------
# Pass 1 — Confidence-weighted accuracy estimate
# ---------------------------------------------------------------------------

def pass1_estimate(results: list[dict]) -> dict[str, Any]:
    """
    Compute a confidence-weighted accuracy estimate.
    Each app's confidence score is mapped to an estimated accuracy and
    averaged across all apps.
    """
    if not results:
        return {"pass1_accuracy_estimate": 0.0, "breakdown": {}, "total": 0}

    weights = []
    breakdown = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    for r in results:
        conf = r.get("confidence", "medium")
        if conf not in CONFIDENCE_ACCURACY:
            conf = "medium"
        breakdown[conf if conf in breakdown else "unknown"] += 1
        weights.append(CONFIDENCE_ACCURACY.get(conf, 0.70))

    estimate = sum(weights) / len(weights)
    console.print(
        f"\n[bold]Pass 1[/bold] — {len(results)} apps loaded. "
        f"Weighted accuracy estimate: [green]{estimate:.1%}[/green]"
    )
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Confidence", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Implied Accuracy", justify="right")
    for level, count in breakdown.items():
        acc = CONFIDENCE_ACCURACY.get(level, 0.70)
        table.add_row(level, str(count), f"{acc:.0%}")
    console.print(table)

    return {
        "pass1_accuracy_estimate": round(estimate, 4),
        "breakdown": breakdown,
        "total": len(results),
    }


# ---------------------------------------------------------------------------
# Pass 2 — Re-research sample
# ---------------------------------------------------------------------------

def pass2_verify(
    results: list[dict],
    client: anthropic.Anthropic,
    sample_size: int = 20,
) -> dict[str, Any]:
    """
    Randomly sample up to sample_size apps (biased toward low/medium confidence),
    re-research each, compare key fields, and return accuracy stats.
    """
    apps_json_path = DATA_DIR / "apps.json"
    apps_lookup: dict[str, dict] = {}
    if apps_json_path.exists():
        for a in json.loads(apps_json_path.read_text()):
            apps_lookup[a["app"].lower()] = a

    # Bias sampling: low/medium first, then high
    low_med = [r for r in results if r.get("confidence") in ("low", "medium")]
    high = [r for r in results if r.get("confidence") == "high"]
    random.shuffle(low_med)
    random.shuffle(high)
    pool = (low_med + high)[:sample_size]

    console.print(
        f"\n[bold]Pass 2[/bold] — Re-researching {len(pool)} apps "
        f"({len(low_med[:sample_size])} low/med + {max(0, sample_size - len(low_med))} high)…"
    )

    pass2_results: list[dict] = []
    agreed_count = 0
    honest_misses: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Verifying…", total=len(pool))

        for r in pool:
            app_name = r.get("app_name", "")
            progress.update(task, description=f"[cyan]Re-checking[/cyan] {app_name}")

            app_entry = apps_lookup.get(app_name.lower(), {"app": app_name, "hint": "", "category": ""})

            try:
                pass2_raw = research_app(
                    app=app_entry,
                    client=client,
                    tier=2,
                    previous_result=r,
                )
            except Exception as exc:
                console.print(f"  [red]✗[/red] {app_name}: {exc}")
                progress.advance(task)
                continue

            agreed, mismatches = _fields_match(r, pass2_raw)
            if agreed:
                agreed_count += 1

            entry = {
                "app": app_name,
                "agreed": agreed,
                "field_mismatches": mismatches,
                "pass1_answer": {f: r.get(f) for f in COMPARE_FIELDS},
                "pass2_answer": {f: pass2_raw.get(f) for f in COMPARE_FIELDS},
                "notes": pass2_raw.get("research_notes") or pass2_raw.get("verification_notes") or "",
            }
            pass2_results.append(entry)

            # Record honest misses (fields that changed between passes)
            for field in mismatches:
                honest_misses.append({
                    "app": app_name,
                    "field": field,
                    "agent_said": r.get(field),
                    "reality": pass2_raw.get(field),
                    "evidence": pass2_raw.get("evidence_url", ""),
                    "correction": f"Pass 2 re-search returned different value for {field}",
                })

            # Persist updated result to data/verified/
            verified_path = VERIFIED_DIR / f"{app_name.lower().replace(' ', '_')}.json"
            _save_json(verified_path, pass2_raw)

            progress.advance(task)

    accuracy = agreed_count / len(pass2_results) if pass2_results else 0.0
    console.print(
        f"  Pass 2 complete — {agreed_count}/{len(pass2_results)} agreed. "
        f"Accuracy: [green]{accuracy:.1%}[/green]"
    )

    return {
        "pass2_accuracy_estimate": round(accuracy, 4),
        "total_checked": len(pass2_results),
        "agreed": agreed_count,
        "results": pass2_results,
        "honest_misses": honest_misses,
    }


# ---------------------------------------------------------------------------
# Pass 3 — Human check placeholder
# ---------------------------------------------------------------------------

def pass3_human_check(results: list[dict], pass2_data: dict) -> list[dict]:
    """
    Identify the 5–10 apps most in need of human review:
    - Low-confidence apps
    - Apps where Pass 2 disagreed
    - Apps with known blockers
    Returns a list saved to data/needs_human_check.json.
    """
    disagreed_apps = {
        entry["app"]
        for entry in pass2_data.get("results", [])
        if not entry["agreed"]
    }

    candidates: list[dict] = []
    for r in results:
        score = 0
        reasons: list[str] = []

        if r.get("confidence") == "low":
            score += 3
            reasons.append("low overall confidence")

        conf_fields = r.get("confidence_per_field", {})
        low_fields = [k for k, v in conf_fields.items() if v == "low"]
        if low_fields:
            score += len(low_fields)
            reasons.append(f"low confidence on: {', '.join(low_fields)}")

        if r.get("app_name") in disagreed_apps:
            score += 4
            reasons.append("Pass 2 disagreed on key fields")

        if r.get("buildability") in ("needs_outreach", "not_buildable"):
            score += 1
            reasons.append(f"buildability={r.get('buildability')}")

        candidates.append({
            "app": r.get("app_name"),
            "score": score,
            "reasons": reasons,
            "evidence_url": r.get("evidence_url", ""),
            "confidence": r.get("confidence", "unknown"),
            "buildability": r.get("buildability", "unknown"),
        })

    # Top 10 by score
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top = candidates[:10]

    console.print(f"\n[bold]Pass 3[/bold] — {len(top)} apps flagged for human review:")
    for c in top:
        console.print(f"  [yellow]⚠[/yellow]  {c['app']} (score={c['score']}): {'; '.join(c['reasons'])}")

    return top


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_verification() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ANTHROPIC_API_KEY not set — aborting.[/red]")
        return

    client = anthropic.Anthropic(api_key=api_key)

    console.rule("[bold cyan]ToolScout — Verification[/bold cyan]")

    # Load all raw results
    results = _load_raw_results()
    if not results:
        console.print("[yellow]No raw results found in data/raw/ — run run.py first.[/yellow]")
        return

    console.print(f"Loaded [bold]{len(results)}[/bold] app results from data/raw/")

    # Pass 1
    p1 = pass1_estimate(results)

    # Pass 2 (skip if no API key or if --skip-pass2 flag found)
    import sys
    skip_pass2 = "--skip-pass2" in sys.argv
    if skip_pass2:
        console.print("\n[dim]Pass 2 skipped (--skip-pass2)[/dim]")
        p2 = {"pass2_accuracy_estimate": None, "total_checked": 0, "agreed": 0, "results": [], "honest_misses": []}
    else:
        p2 = pass2_verify(results, client, sample_size=20)

    # Pass 3
    needs_human = pass3_human_check(results, p2)

    # Build report
    report = {
        "pass1_accuracy_estimate": p1["pass1_accuracy_estimate"],
        "pass2_accuracy_estimate": p2["pass2_accuracy_estimate"],
        "pass3_accuracy_final": None,  # filled in after human review
        "total_apps": p1["total"],
        "total_checked_pass2": p2["total_checked"],
        "confidence_breakdown": p1["breakdown"],
        "timestamp": datetime.utcnow().isoformat(),
        "results": p2["results"],
    }

    _save_json(DATA_DIR / "verification_report.json", report)
    _save_json(DATA_DIR / "honest_misses.json", p2["honest_misses"])
    _save_json(DATA_DIR / "needs_human_check.json", needs_human)

    console.rule()
    console.print("[bold green]Verification complete[/bold green]")
    console.print(f"  Pass 1 estimate : {p1['pass1_accuracy_estimate']:.1%}")
    if p2["pass2_accuracy_estimate"] is not None:
        console.print(f"  Pass 2 accuracy : {p2['pass2_accuracy_estimate']:.1%}")
    console.print(f"  Honest misses   : {len(p2['honest_misses'])}")
    console.print(f"  Human review    : {len(needs_human)} apps → data/needs_human_check.json")
    console.print()
    console.print("  data/verification_report.json ✓")
    console.print("  data/honest_misses.json ✓")
    console.print("  data/needs_human_check.json ✓")


if __name__ == "__main__":
    run_verification()
