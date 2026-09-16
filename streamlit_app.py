"""
ToolScout — Live Streamlit demo.

Enter any app name, click Research, and get a structured JSON result
with color-coded confidence, tier used, and evidence URL — all live.
"""

from __future__ import annotations

import json
import os
import time

import anthropic
import streamlit as st
from dotenv import load_dotenv

from agent import research_app
from schema import AppResearch

load_dotenv()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ToolScout — Live Demo",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  .block-container { max-width: 900px; padding-top: 2rem; }
  .toolscout-title {
    font-size: 2.2rem; font-weight: 800;
    background: linear-gradient(90deg, #6C63FF, #8B85FF);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.2rem;
  }
  .badge {
    display: inline-block; padding: 2px 10px; border-radius: 4px;
    font-size: 0.75rem; font-weight: 700; font-family: monospace; margin: 2px;
  }
  .badge-high { background: #22C55E22; color: #22C55E; }
  .badge-medium { background: #F59E0B22; color: #F59E0B; }
  .badge-low { background: #EF444422; color: #EF4444; }
  .badge-ready { background: #22C55E22; color: #22C55E; }
  .badge-needs_outreach { background: #F59E0B22; color: #F59E0B; }
  .badge-not_buildable { background: #EF444422; color: #EF4444; }
  .badge-non_standard { background: #6C63FF22; color: #6C63FF; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar — API key entry
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ToolScout Settings")
    api_key_input = st.text_input(
        "Anthropic API Key",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Loaded from .env if present.",
    )
    st.markdown("---")
    st.markdown("**About ToolScout**")
    st.markdown(
        "ToolScout uses Claude + web search to research any app's "
        "API auth method, access model, MCP availability, and buildability "
        "for Composio's integration pipeline."
    )
    st.markdown("---")
    st.caption("Model: claude-sonnet-4-6 · Tool: web_search_20250305")


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown('<div class="toolscout-title">ToolScout</div>', unsafe_allow_html=True)
st.markdown(
    "**Live API research for Composio's integration pipeline.** "
    "Enter any app and get structured intelligence in seconds."
)
st.markdown("---")


# ---------------------------------------------------------------------------
# Input row
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns([3, 2, 1])
with col1:
    app_name = st.text_input(
        "App name",
        placeholder="e.g. Linear, Stripe, Notion…",
        label_visibility="collapsed",
    )
with col2:
    hint = st.text_input(
        "API docs URL (optional)",
        placeholder="docs.example.com",
        label_visibility="collapsed",
    )
with col3:
    go = st.button("Research →", type="primary", use_container_width=True)


# ---------------------------------------------------------------------------
# Research and display
# ---------------------------------------------------------------------------
if go and app_name.strip():
    key = api_key_input.strip() or os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        st.error("Set your ANTHROPIC_API_KEY in the sidebar or .env file.")
        st.stop()

    client = anthropic.Anthropic(api_key=key)
    app_entry = {
        "app": app_name.strip(),
        "hint": hint.strip(),
        "category": "Unknown",
    }

    with st.spinner(f"ToolScout is researching **{app_name}**…"):
        t0 = time.time()
        try:
            result = research_app(app=app_entry, client=client, tier=2)
            elapsed = time.time() - t0
        except Exception as exc:
            st.error(f"Research failed: {exc}")
            st.stop()

    # ---------------------------------------------------------------------------
    # Summary cards
    # ---------------------------------------------------------------------------
    st.success(f"Research complete in {elapsed:.1f}s — Tier {result.get('tier_used', 2)}")

    m1, m2, m3, m4 = st.columns(4)
    build = result.get("buildability", "unknown")
    conf = result.get("confidence", "unknown")
    score = result.get("opportunity_score", 0)
    mcp = result.get("mcp_exists", False)

    build_color = {"ready": "🟢", "needs_outreach": "🟡", "not_buildable": "🔴", "non_standard": "🟣"}
    conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}

    m1.metric("Buildability", f"{build_color.get(build, '⚪')} {build}")
    m2.metric("Opportunity Score", f"{score} / 5")
    m3.metric("Confidence", f"{conf_color.get(conf, '⚪')} {conf}")
    m4.metric("MCP Server", "✓ Exists" if mcp else "✗ None")

    st.markdown("---")

    # ---------------------------------------------------------------------------
    # Detail columns
    # ---------------------------------------------------------------------------
    left, right = st.columns([1, 1])

    with left:
        st.markdown("#### API Details")
        st.markdown(f"**One-liner:** {result.get('one_liner', '')}")
        st.markdown(f"**Auth methods:** `{'`, `'.join(result.get('auth_methods', []))}`")
        st.markdown(f"**API type:** `{result.get('api_type', '')}`")
        st.markdown(f"**API breadth:** `{result.get('api_breadth', '')}`")
        st.markdown("---")
        st.markdown("#### Access Model")
        self_serve = result.get("self_serve", False)
        trial = result.get("trial_available", False)
        st.markdown(f"**Self-serve:** {'✅ Yes' if self_serve else '❌ No'}")
        st.markdown(f"**Trial available:** {'✅ Yes' if trial else '❌ No'}")
        st.markdown(f"**Gating note:** {result.get('gating_note', '')}")

    with right:
        st.markdown("#### MCP")
        if mcp:
            st.markdown(f"**MCP URL:** [{result.get('mcp_url','')}]({result.get('mcp_url','')})")
        else:
            st.markdown("No published MCP server found.")

        if result.get("blocker"):
            st.warning(f"**Blocker:** {result.get('blocker')}")

        st.markdown("---")
        st.markdown("#### Confidence Per Field")
        cpf = result.get("confidence_per_field", {})
        conf_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}
        for field, level in cpf.items():
            st.markdown(f"{conf_icon.get(level, '⚪')} **{field}**: `{level}`")

        st.markdown("---")
        st.markdown("#### Evidence")
        ev_url = result.get("evidence_url", "#")
        st.markdown(f"[{ev_url}]({ev_url})")
        st.caption(f"Source: `{result.get('source', '')}` · Tier {result.get('tier_used', 2)}")

    # ---------------------------------------------------------------------------
    # Raw JSON
    # ---------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("Raw JSON output"):
        st.json(result)

elif go:
    st.warning("Enter an app name first.")


# ---------------------------------------------------------------------------
# Footer — example apps
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    "Try: Stripe · Linear · Notion · Shopify · DataForSEO · Lark · Grain · Reducto"
)
