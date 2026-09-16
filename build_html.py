"""
ToolScout — Standalone HTML report generator.

Reads data/final.json + data/verification_report.json and produces
a single self-contained index.html in Composio's brand theme.

Sections:
  1. Hero — headline stats
  2. How It Works — 3-tier diagram
  3. Opportunity Matrix — 2×2 SVG scatter (self_serve × api_breadth)
  4. Full Results Table — filterable, sortable
  5. Category Breakdown — bar chart (inline SVG)
  6. Auth Methods — frequency chart (inline SVG)
  7. MCP Landscape — MCP-ready vs gap analysis
  8. Honest Misses — what the agent got wrong or wasn't sure about
  9. Verification Accuracy — pass scores + methodology
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path("data")


# ---------------------------------------------------------------------------
# Composio brand palette
# ---------------------------------------------------------------------------
BRAND = {
    "bg": "#0A0A0A",
    "surface": "#111111",
    "surface2": "#1A1A1A",
    "border": "#2A2A2A",
    "primary": "#6C63FF",
    "primary_light": "#8B85FF",
    "green": "#22C55E",
    "yellow": "#F59E0B",
    "red": "#EF4444",
    "text": "#F5F5F5",
    "muted": "#888888",
    "subtle": "#444444",
}

BUILDABILITY_COLOR = {
    "ready": BRAND["green"],
    "needs_outreach": BRAND["yellow"],
    "not_buildable": BRAND["red"],
    "non_standard": BRAND["primary"],
}

CONFIDENCE_COLOR = {
    "high": BRAND["green"],
    "medium": BRAND["yellow"],
    "low": BRAND["red"],
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load(path: Path) -> any:
    if path.exists():
        return json.loads(path.read_text())
    return None


def load_data() -> tuple[list[dict], dict | None]:
    final = _load(DATA_DIR / "final.json") or []
    report = _load(DATA_DIR / "verification_report.json")
    return final, report


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------

def _opportunity_matrix_svg(results: list[dict]) -> str:
    """2×2 scatter: x=api_breadth, y=self_serve, color=buildability."""
    breadth_x = {"none": 0.15, "narrow": 0.35, "moderate": 0.65, "broad": 0.85}
    W, H = 480, 340
    pad = 48

    dots: list[str] = []
    tooltips: list[str] = []

    for r in results:
        bx = breadth_x.get(r.get("api_breadth", "narrow"), 0.35)
        by_val = 0.75 if r.get("self_serve") else 0.25
        # Add jitter to avoid exact overlaps
        import hashlib
        h = int(hashlib.md5(r.get("app_name", "x").encode()).hexdigest()[:4], 16)
        jx = ((h % 40) - 20) / 1000
        jy = ((h // 40 % 40) - 20) / 1000

        cx = pad + (bx + jx) * (W - 2 * pad)
        cy = H - pad - (by_val + jy) * (H - 2 * pad)
        color = BUILDABILITY_COLOR.get(r.get("buildability", "ready"), BRAND["primary"])
        score = r.get("opportunity_score", 3)
        radius = 4 + score * 1.2

        app = r.get("app_name", "")
        dots.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" '
            f'fill="{color}" fill-opacity="0.8" stroke="{BRAND["border"]}" stroke-width="1">'
            f'<title>{app} | score={score} | {r.get("buildability","")}</title>'
            f'</circle>'
        )

    # Axes
    axis_style = f'stroke="{BRAND["subtle"]}" stroke-width="1" stroke-dasharray="4,4"'
    mid_x = pad + 0.5 * (W - 2 * pad)
    mid_y = H - pad - 0.5 * (H - 2 * pad)
    lines = (
        f'<line x1="{mid_x}" y1="{pad}" x2="{mid_x}" y2="{H - pad}" {axis_style}/>'
        f'<line x1="{pad}" y1="{mid_y}" x2="{W - pad}" y2="{mid_y}" {axis_style}/>'
    )

    label_style = f'fill="{BRAND["muted"]}" font-size="10" font-family="monospace"'
    labels = (
        f'<text x="{pad}" y="{H - 6}" {label_style}>narrow</text>'
        f'<text x="{W - pad - 30}" y="{H - 6}" {label_style}>broad</text>'
        f'<text x="4" y="{H - pad}" {label_style} text-anchor="start">gated</text>'
        f'<text x="4" y="{pad + 12}" {label_style} text-anchor="start">self-serve</text>'
    )

    legend_items = [
        ("ready", BUILDABILITY_COLOR["ready"]),
        ("needs_outreach", BUILDABILITY_COLOR["needs_outreach"]),
        ("not_buildable", BUILDABILITY_COLOR["not_buildable"]),
        ("non_standard", BUILDABILITY_COLOR["non_standard"]),
    ]
    legend = ""
    for i, (label, color) in enumerate(legend_items):
        lx = pad + i * 110
        legend += (
            f'<circle cx="{lx + 6}" cy="{H - 18}" r="5" fill="{color}"/>'
            f'<text x="{lx + 14}" y="{H - 14}" fill="{BRAND["muted"]}" font-size="10" '
            f'font-family="monospace">{label}</text>'
        )

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;max-width:{W}px;background:{BRAND["surface2"]};'
        f'border-radius:8px;border:1px solid {BRAND["border"]}">'
        + lines + labels + "".join(dots) + legend
        + "</svg>"
    )


def _bar_chart_svg(counts: dict[str, int], title: str, color: str) -> str:
    """Horizontal bar chart."""
    items = sorted(counts.items(), key=lambda x: -x[1])[:12]
    if not items:
        return ""
    max_val = max(v for _, v in items)
    row_h = 28
    label_w = 180
    bar_area = 220
    W = label_w + bar_area + 60
    H = len(items) * row_h + 24

    bars = ""
    for i, (label, val) in enumerate(items):
        y = i * row_h + 12
        bar_w = (val / max_val) * bar_area if max_val else 0
        bars += (
            f'<text x="{label_w - 6}" y="{y + 13}" fill="{BRAND["text"]}" '
            f'font-size="11" font-family="sans-serif" text-anchor="end">{label[:28]}</text>'
            f'<rect x="{label_w}" y="{y + 2}" width="{bar_w:.1f}" height="18" '
            f'fill="{color}" rx="3"/>'
            f'<text x="{label_w + bar_w + 4}" y="{y + 14}" fill="{BRAND["muted"]}" '
            f'font-size="10" font-family="monospace">{val}</text>'
        )

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;max-width:{W}px">'
        + bars + "</svg>"
    )


# ---------------------------------------------------------------------------
# HTML sections
# ---------------------------------------------------------------------------

def _badge(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
        f'background:{color}22;color:{color};font-size:11px;font-weight:600;'
        f'font-family:monospace">{text}</span>'
    )


def _section(title: str, content: str, id: str = "") -> str:
    id_attr = f' id="{id}"' if id else ""
    return f"""
<section{id_attr} style="margin:48px 0">
  <h2 style="font-size:22px;font-weight:700;margin:0 0 20px;color:{BRAND["text"]};
     border-left:3px solid {BRAND["primary"]};padding-left:12px">{title}</h2>
  {content}
</section>
"""


def _hero(results: list[dict], report: dict | None) -> str:
    total = len(results)
    ready = sum(1 for r in results if r.get("buildability") == "ready")
    mcp = sum(1 for r in results if r.get("mcp_exists"))
    self_serve = sum(1 for r in results if r.get("self_serve"))
    p1 = report.get("pass1_accuracy_estimate", 0) if report else 0
    p2 = report.get("pass2_accuracy_estimate") if report else None

    acc_str = f"{p1:.0%}"
    if p2 is not None:
        acc_str = f"{p2:.0%} (verified)"

    stats = [
        ("Apps Researched", str(total), BRAND["primary"]),
        ("Ready to Build", str(ready), BRAND["green"]),
        ("MCP Servers Found", str(mcp), BRAND["primary_light"]),
        ("Self-Serve APIs", str(self_serve), BRAND["green"]),
        ("Verification Accuracy", acc_str, BRAND["yellow"]),
    ]

    cards = ""
    for label, val, color in stats:
        cards += f"""
<div style="background:{BRAND["surface2"]};border:1px solid {BRAND["border"]};
  border-radius:12px;padding:24px 28px;flex:1;min-width:140px">
  <div style="font-size:32px;font-weight:800;color:{color};font-variant-numeric:tabular-nums">{val}</div>
  <div style="font-size:13px;color:{BRAND["muted"]};margin-top:6px">{label}</div>
</div>"""

    return f"""
<div style="background:linear-gradient(135deg,{BRAND["surface2"]} 0%,{BRAND["bg"]} 100%);
  border:1px solid {BRAND["border"]};border-radius:16px;padding:48px 36px;margin-bottom:48px">
  <div style="font-size:13px;color:{BRAND["primary"]};font-weight:600;
    letter-spacing:0.1em;text-transform:uppercase;margin-bottom:12px">
    ToolScout by Composio
  </div>
  <h1 style="font-size:38px;font-weight:800;color:{BRAND["text"]};margin:0 0 12px;
    line-height:1.2">100 App Integration Intelligence Report</h1>
  <p style="color:{BRAND["muted"]};font-size:16px;margin:0 0 36px;max-width:600px">
    Which apps are ready to turn into AI agent tools? ToolScout researched 100 apps
    across auth, API surface, self-serve access, and MCP availability.
  </p>
  <div style="display:flex;flex-wrap:wrap;gap:16px">{cards}</div>
</div>"""


def _how_it_works() -> str:
    tiers = [
        ("Tier 1", "Composio Native", "Is the app already an integration? Instant high-confidence result.", BRAND["green"]),
        ("Tier 2", "Web Search", "Uses Claude + web_search to find API docs, auth method, pricing, MCP.", BRAND["primary"]),
        ("Tier 3", "Deep Fetch", "Triggered on low/medium confidence. Re-researches with verification prompt.", BRAND["yellow"]),
    ]
    cards = ""
    for tier, name, desc, color in tiers:
        cards += f"""
<div style="flex:1;min-width:200px;background:{BRAND["surface2"]};border:1px solid {BRAND["border"]};
  border-top:3px solid {color};border-radius:8px;padding:20px">
  <div style="font-size:11px;font-weight:700;color:{color};text-transform:uppercase;
    letter-spacing:0.1em;margin-bottom:6px">{tier}</div>
  <div style="font-size:16px;font-weight:700;color:{BRAND["text"]};margin-bottom:8px">{name}</div>
  <div style="font-size:13px;color:{BRAND["muted"]};line-height:1.6">{desc}</div>
</div>"""
    return _section(
        "How ToolScout Works",
        f'<div style="display:flex;gap:16px;flex-wrap:wrap">{cards}</div>',
        id="how-it-works",
    )


def _opportunity_section(results: list[dict]) -> str:
    svg = _opportunity_matrix_svg(results)
    desc = f"""
<p style="color:{BRAND["muted"]};font-size:14px;margin:0 0 20px">
  Each dot is one app. X-axis = API breadth (narrow → broad).
  Y-axis = access model (gated vs self-serve). Dot size = opportunity score.
  Color = buildability.
</p>"""
    return _section("Opportunity Matrix", desc + svg, id="matrix")


def _results_table(results: list[dict]) -> str:
    rows = ""
    for r in sorted(results, key=lambda x: -x.get("opportunity_score", 0)):
        app = r.get("app_name", "")
        cat = r.get("category", "")
        build = r.get("buildability", "")
        conf = r.get("confidence", "")
        score = r.get("opportunity_score", 0)
        mcp = "✓" if r.get("mcp_exists") else "–"
        auth = ", ".join(r.get("auth_methods", [])[:2])
        ev = r.get("evidence_url", "#")

        build_badge = _badge(build, BUILDABILITY_COLOR.get(build, BRAND["subtle"]))
        conf_badge = _badge(conf, CONFIDENCE_COLOR.get(conf, BRAND["subtle"]))
        score_color = BRAND["green"] if score >= 4 else (BRAND["yellow"] if score >= 3 else BRAND["red"])

        rows += f"""
<tr style="border-bottom:1px solid {BRAND["border"]}">
  <td style="padding:10px 12px;font-weight:600;color:{BRAND["text"]}">{app}</td>
  <td style="padding:10px 12px;color:{BRAND["muted"]};font-size:12px">{cat}</td>
  <td style="padding:10px 12px">{build_badge}</td>
  <td style="padding:10px 12px;color:{score_color};font-weight:700;font-size:18px">{score}</td>
  <td style="padding:10px 12px;color:{BRAND["text"]};font-size:12px">{auth}</td>
  <td style="padding:10px 12px;color:{BRAND["primary"]};font-size:14px">{mcp}</td>
  <td style="padding:10px 12px">{conf_badge}</td>
  <td style="padding:10px 12px">
    <a href="{ev}" target="_blank" rel="noopener"
       style="color:{BRAND["primary"]};font-size:11px;text-decoration:none">docs ↗</a>
  </td>
</tr>"""

    header_style = f'style="padding:10px 12px;color:{BRAND["muted"]};font-size:11px;text-transform:uppercase;letter-spacing:0.08em;text-align:left;border-bottom:1px solid {BRAND["border"]}"'
    thead = f"""
<thead>
  <tr>
    <th {header_style}>App</th>
    <th {header_style}>Category</th>
    <th {header_style}>Buildability</th>
    <th {header_style}>Score</th>
    <th {header_style}>Auth</th>
    <th {header_style}>MCP</th>
    <th {header_style}>Confidence</th>
    <th {header_style}>Docs</th>
  </tr>
</thead>"""

    filter_js = """
<script>
function filterTable(val) {
  const q = val.toLowerCase();
  document.querySelectorAll('#results-table tbody tr').forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}
function filterBuild(val) {
  document.querySelectorAll('#results-table tbody tr').forEach(row => {
    if (!val) { row.style.display = ''; return; }
    row.style.display = row.children[2].textContent.trim().includes(val) ? '' : 'none';
  });
}
</script>
"""

    controls = f"""
<div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap">
  <input type="text" placeholder="Filter apps…" oninput="filterTable(this.value)"
    style="background:{BRAND["surface2"]};border:1px solid {BRAND["border"]};color:{BRAND["text"]};
    padding:8px 12px;border-radius:6px;font-size:13px;width:220px;outline:none"/>
  <select onchange="filterBuild(this.value)"
    style="background:{BRAND["surface2"]};border:1px solid {BRAND["border"]};color:{BRAND["text"]};
    padding:8px 12px;border-radius:6px;font-size:13px;cursor:pointer;outline:none">
    <option value="">All buildability</option>
    <option value="ready">Ready</option>
    <option value="needs_outreach">Needs Outreach</option>
    <option value="not_buildable">Not Buildable</option>
    <option value="non_standard">Non-Standard</option>
  </select>
</div>"""

    table = f"""
<div style="overflow-x:auto">
<table id="results-table" style="width:100%;border-collapse:collapse;font-size:13px">
  {thead}
  <tbody>{rows}</tbody>
</table>
</div>"""

    return _section("All Results", filter_js + controls + table, id="results")


def _category_section(results: list[dict]) -> str:
    cats = Counter(r.get("category", "Unknown") for r in results)
    svg = _bar_chart_svg(dict(cats), "By Category", BRAND["primary"])
    return _section("Apps by Category", svg, id="categories")


def _auth_section(results: list[dict]) -> str:
    auth_counts: Counter = Counter()
    for r in results:
        for m in r.get("auth_methods", []):
            auth_counts[m] += 1
    svg = _bar_chart_svg(dict(auth_counts), "Auth Methods", BRAND["primary_light"])
    return _section("Auth Method Distribution", svg, id="auth")


def _mcp_section(results: list[dict]) -> str:
    with_mcp = [r for r in results if r.get("mcp_exists")]
    without_mcp = [r for r in results if not r.get("mcp_exists") and r.get("buildability") == "ready"]

    mcp_rows = ""
    for r in with_mcp:
        url = r.get("mcp_url") or "#"
        mcp_rows += f"""
<tr style="border-bottom:1px solid {BRAND["border"]}">
  <td style="padding:8px 12px;font-weight:600;color:{BRAND["text"]}">{r.get("app_name")}</td>
  <td style="padding:8px 12px">
    <a href="{url}" target="_blank" rel="noopener"
       style="color:{BRAND["primary"]};font-size:12px">{url[:60]}</a>
  </td>
</tr>"""

    gap_rows = ""
    for r in without_mcp[:15]:
        gap_rows += f"""
<tr style="border-bottom:1px solid {BRAND["border"]}">
  <td style="padding:8px 12px;color:{BRAND["text"]}">{r.get("app_name")}</td>
  <td style="padding:8px 12px;color:{BRAND["muted"]};font-size:12px">{r.get("category","")}</td>
  <td style="padding:8px 12px;color:{BRAND["yellow"]};font-size:12px">
    {r.get("api_breadth","")}</td>
</tr>"""

    th = f'style="padding:8px 12px;color:{BRAND["muted"]};font-size:11px;text-transform:uppercase;border-bottom:1px solid {BRAND["border"]};text-align:left"'
    content = f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;flex-wrap:wrap">
  <div>
    <h3 style="font-size:15px;font-weight:600;color:{BRAND["green"]};margin:0 0 12px">
      {len(with_mcp)} Apps With MCP Servers
    </h3>
    <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr><th {th}>App</th><th {th}>MCP URL</th></tr></thead>
      <tbody>{mcp_rows or '<tr><td colspan="2" style="padding:12px;color:' + BRAND["muted"] + '">None found yet</td></tr>'}</tbody>
    </table>
    </div>
  </div>
  <div>
    <h3 style="font-size:15px;font-weight:600;color:{BRAND["yellow"]};margin:0 0 12px">
      Top MCP Gaps (ready but no MCP)
    </h3>
    <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr><th {th}>App</th><th {th}>Category</th><th {th}>API Breadth</th></tr></thead>
      <tbody>{gap_rows or '<tr><td colspan="3" style="padding:12px;color:' + BRAND["muted"] + '">None identified</td></tr>'}</tbody>
    </table>
    </div>
  </div>
</div>"""
    return _section("MCP Landscape", content, id="mcp")


def _honest_misses_section() -> str:
    misses_path = DATA_DIR / "honest_misses.json"
    misses = json.loads(misses_path.read_text()) if misses_path.exists() else []
    if not misses:
        content = f'<p style="color:{BRAND["muted"]}">No misses recorded — verification pass not yet run.</p>'
        return _section("Honest Misses", content, id="misses")

    rows = ""
    for m in misses[:20]:
        rows += f"""
<tr style="border-bottom:1px solid {BRAND["border"]}">
  <td style="padding:8px 12px;font-weight:600;color:{BRAND["text"]}">{m.get("app")}</td>
  <td style="padding:8px 12px;color:{BRAND["yellow"]};font-family:monospace;font-size:12px">{m.get("field")}</td>
  <td style="padding:8px 12px;color:{BRAND["red"]};font-size:12px">{json.dumps(m.get("agent_said"))}</td>
  <td style="padding:8px 12px;color:{BRAND["green"]};font-size:12px">{json.dumps(m.get("reality"))}</td>
  <td style="padding:8px 12px;color:{BRAND["muted"]};font-size:11px">{m.get("correction","")[:80]}</td>
</tr>"""

    th = f'style="padding:8px 12px;color:{BRAND["muted"]};font-size:11px;text-transform:uppercase;border-bottom:1px solid {BRAND["border"]};text-align:left"'
    content = f"""
<p style="color:{BRAND["muted"]};font-size:13px;margin:0 0 16px">
  Fields where Pass 2 verification disagreed with the initial Pass 1 answer.
  These are real limitations of automated research — not bugs, just honest uncertainty.
</p>
<div style="overflow-x:auto">
<table style="width:100%;border-collapse:collapse;font-size:13px">
  <thead><tr>
    <th {th}>App</th><th {th}>Field</th>
    <th {th}>Agent Said</th><th {th}>Corrected To</th><th {th}>Note</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
</div>"""
    return _section(f"Honest Misses ({len(misses)} total)", content, id="misses")


def _verification_section(report: dict | None) -> str:
    if not report:
        content = f'<p style="color:{BRAND["muted"]}">Verification not yet run.</p>'
        return _section("Verification Accuracy", content, id="verification")

    p1 = report.get("pass1_accuracy_estimate", 0)
    p2 = report.get("pass2_accuracy_estimate")
    p3 = report.get("pass3_accuracy_final")
    total = report.get("total_apps", 0)
    checked = report.get("total_checked_pass2", 0)
    breakdown = report.get("confidence_breakdown", {})

    passes = [
        ("Pass 1", "Confidence-weighted estimate",
         f"{p1:.0%}", "Accuracy inferred from agent's own confidence scores (high=90%, medium=70%, low=50%)", BRAND["yellow"]),
        ("Pass 2", f"Re-research sample ({checked} apps)",
         f"{p2:.0%}" if p2 is not None else "—",
         "Randomly sampled 20 apps (biased toward low/medium), re-ran research, compared 4 key fields", BRAND["primary"]),
        ("Pass 3", "Human review",
         f"{p3:.0%}" if p3 is not None else "Pending",
         "Manual spot-check of flagged apps. See data/needs_human_check.json.", BRAND["green"]),
    ]

    cards = ""
    for name, subtitle, val, desc, color in passes:
        cards += f"""
<div style="flex:1;min-width:200px;background:{BRAND["surface2"]};border:1px solid {BRAND["border"]};
  border-top:3px solid {color};border-radius:8px;padding:20px">
  <div style="font-size:11px;font-weight:700;color:{color};text-transform:uppercase;
    letter-spacing:0.1em;margin-bottom:4px">{name}</div>
  <div style="font-size:12px;color:{BRAND["muted"]};margin-bottom:12px">{subtitle}</div>
  <div style="font-size:36px;font-weight:800;color:{BRAND["text"]};margin-bottom:8px">{val}</div>
  <div style="font-size:12px;color:{BRAND["muted"]};line-height:1.5">{desc}</div>
</div>"""

    bdown_html = ""
    for level, count in breakdown.items():
        color = CONFIDENCE_COLOR.get(level, BRAND["subtle"])
        bdown_html += (
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
            f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{color}"></span>'
            f'<span style="color:{BRAND["text"]};font-size:13px;width:60px">{level}</span>'
            f'<span style="color:{BRAND["muted"]};font-size:13px">{count} apps</span></div>'
        )

    content = f"""
<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px">{cards}</div>
<div style="background:{BRAND["surface2"]};border:1px solid {BRAND["border"]};border-radius:8px;
  padding:20px;display:inline-block">
  <div style="font-size:13px;font-weight:600;color:{BRAND["text"]};margin-bottom:12px">
    Confidence Distribution ({total} apps)
  </div>
  {bdown_html}
</div>"""
    return _section("Verification Accuracy", content, id="verification")


# ---------------------------------------------------------------------------
# Nav + full page assembly
# ---------------------------------------------------------------------------

def _nav() -> str:
    links = [
        ("#how-it-works", "How It Works"),
        ("#matrix", "Opportunity Matrix"),
        ("#results", "All Results"),
        ("#categories", "Categories"),
        ("#auth", "Auth Methods"),
        ("#mcp", "MCP Landscape"),
        ("#misses", "Honest Misses"),
        ("#verification", "Verification"),
    ]
    items = "".join(
        f'<a href="{href}" style="color:{BRAND["muted"]};text-decoration:none;font-size:13px;'
        f'padding:6px 12px;border-radius:6px;transition:color 0.2s" '
        f'onmouseover="this.style.color=\'{BRAND["text"]}\'" '
        f'onmouseout="this.style.color=\'{BRAND["muted"]}\'">{label}</a>'
        for href, label in links
    )
    return f"""
<nav style="position:sticky;top:0;z-index:100;background:{BRAND["bg"]}CC;
  backdrop-filter:blur(12px);border-bottom:1px solid {BRAND["border"]};
  padding:12px 48px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
  <span style="font-weight:800;color:{BRAND["primary"]};font-size:15px;margin-right:16px">
    ToolScout
  </span>
  {items}
</nav>"""


def build_html(results: list[dict], report: dict | None) -> str:
    sections = (
        _hero(results, report)
        + _how_it_works()
        + _opportunity_section(results)
        + _results_table(results)
        + _category_section(results)
        + _auth_section(results)
        + _mcp_section(results)
        + _honest_misses_section()
        + _verification_section(report)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>ToolScout — Composio Integration Intelligence Report</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:{BRAND["bg"]};color:{BRAND["text"]};font-family:-apple-system,BlinkMacSystemFont,
  "Segoe UI",Roboto,sans-serif;line-height:1.6}}
::-webkit-scrollbar{{width:6px;height:6px}}
::-webkit-scrollbar-track{{background:{BRAND["surface"]}}}
::-webkit-scrollbar-thumb{{background:{BRAND["subtle"]};border-radius:3px}}
a{{color:{BRAND["primary"]}}}
table tr:hover{{background:{BRAND["surface2"]}55}}
</style>
</head>
<body>
{_nav()}
<main style="max-width:1100px;margin:0 auto;padding:48px 24px">
{sections}
<footer style="margin-top:64px;padding-top:24px;border-top:1px solid {BRAND["border"]};
  color:{BRAND["muted"]};font-size:12px;text-align:center">
  Generated by ToolScout for Composio — {report.get("timestamp","")[:10] if report else ""}
</footer>
</main>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    results, report = load_data()
    if not results:
        print("No data/final.json found. Run run.py first.")
        return

    html = build_html(results, report)
    out = Path("index.html")
    out.write_text(html, encoding="utf-8")
    print(f"index.html written — {len(results)} apps, {len(html):,} bytes")


if __name__ == "__main__":
    main()
