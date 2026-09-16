# ToolScout

**AI-powered API research pipeline for Composio's integration catalog.**

ToolScout researches 100 apps across auth method, self-serve access, API surface, MCP availability, and buildability — producing structured JSON optimized for Composio's agent toolkit pipeline.

Live report: [GitHub Pages](https://yashuburdak.github.io/toolscout/)

---

## Architecture

```
apps.json (100 apps)
       │
       ▼
┌──────────────────────────────────────────────────┐
│  run.py — Batched runner (3-tier strategy)       │
│                                                  │
│  Tier 1 → composio_tier.py                       │
│    Already on Composio? → instant stub (high ✓)  │
│    Live catalog: ~1,945 integrations fetched     │
│                                                  │
│  Tier 2 → agent.py + web_search_preview          │
│    GPT-4o searches API docs, auth, MCP, pricing  │
│                                                  │
│  Tier 3 → agent.py (deep verify)                 │
│    Triggered on low/medium confidence            │
└────────────────┬─────────────────────────────────┘
                 │  data/raw/*.json
                 ▼
┌──────────────────────────────────────────────────┐
│  verify.py — Three-pass verification             │
│    Pass 1: confidence-weighted accuracy estimate │
│    Pass 2: 20-app re-research sample             │
│    Pass 3: human check flagging                  │
└────────────────┬─────────────────────────────────┘
                 │  data/final.json
                 ▼
┌──────────────────────────────────────────────────┐
│  build_html.py → index.html (standalone report)  │
│  generate_pdf.py → ToolScout_CaseStudy.pdf       │
│  streamlit_app.py → live research demo           │
└──────────────────────────────────────────────────┘
```

---

## Setup (3 commands)

```bash
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_API_KEY and COMPOSIO_API_KEY
python run.py
```

To view the live demo:

```bash
streamlit run streamlit_app.py
```

To build the HTML report (after run.py completes):

```bash
python verify.py
python build_html.py
open index.html
```

To generate the PDF case study:

```bash
python generate_pdf.py
```

---

## Output Files

| File | Description |
|------|-------------|
| `data/raw/*.json` | Per-app research cache (100 files) |
| `data/verified/*.json` | Pass 2 corrected results |
| `data/final.json` | Merged final dataset |
| `data/prevalidation.json` | Anchor app validation (Stripe, GitHub, Notion, Slack, Salesforce) |
| `data/verification_report.json` | Pass 1–3 accuracy scores |
| `data/honest_misses.json` | Fields where Pass 2 disagreed with Pass 1 |
| `data/needs_human_check.json` | Top 10 apps flagged for manual review |
| `index.html` | Standalone visual report |
| `ToolScout_CaseStudy.pdf` | PDF case study for submission |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI Research | GPT-4o via OpenAI Python SDK (`web_search_preview` tool) |
| Composio Check | Composio v3 REST API (live catalog, ~1,945 integrations) |
| Verification | Three-pass: confidence-weighted + re-research sample + human flags |
| Output | Standalone HTML report + PDF case study + Streamlit demo |
| Resume support | Per-app JSON cache — safe to interrupt and restart |

---

## Key Design Choices

**Composio-first (Tier 1):** Checks the live Composio REST API (`/api/v3/toolkits`) before spending any web search quota. ~40 apps resolve instantly with `confidence='high'`. The catalog indexes slug, name, and displayName fields for robust matching.

**GPT-4o web search (Tier 2):** Uses the OpenAI Responses API with `web_search_preview` to research API docs, auth schemes, MCP availability, and pricing. Results are parsed into structured `AppResearch` JSON.

**Deep verification (Tier 3):** Low/medium confidence results trigger a second GPT-4o pass with more targeted prompts to resolve ambiguities.

**Resume support:** Each app is cached to `data/raw/{app}.json` before processing. Re-running `run.py` skips already-researched apps — safe to interrupt and resume.

**Manual stubs:** Apps with no public API, CLI-only tooling, or known blockers (Sherlock, Mermaid CLI, Fanbasis, etc.) are written directly as `source='manual'` stubs. The agent doesn't waste API calls on known non-starters. 38 stubs total.

---

## Coverage

- **100/100 apps** researched and resolved
- **~40 apps** resolved via Composio native catalog (Tier 1, instant)
- **~22 apps** researched via GPT-4o web search (Tier 2)
- **38 apps** resolved via manual stubs (known blockers + Composio fallbacks)
- **10 apps** flagged for human review (Pass 3)

---

## Honest Failures

These are real limitations of automated research:

- **Gated docs:** Several enterprise apps (PitchBook, DealCloud, Gladly) have API docs behind sales contracts. The agent correctly reports `buildability='needs_outreach'` and `confidence='low'`.
- **Auth ambiguity:** Some apps advertise both OAuth2 and API Key; the agent may pick one. Pass 2 catches most of these.
- **MCP false negatives:** The agent searches smithery.ai, npm, and GitHub — but private/unpublished MCP servers won't appear. `mcp_exists=False` means "not found publicly," not "definitely doesn't exist."
- **Pricing changes:** Freemium tiers change often. `trial_available` reflects the state at research time.
- **API quota:** GPT-4o and Composio API credits can exhaust mid-run. The resume system and manual stubs ensure 100% coverage regardless.

See `data/honest_misses.json` for specific field-level corrections from Pass 2.

---

## Verification Accuracy

Three passes:

1. **Pass 1** — Confidence-weighted estimate. The agent rates its own confidence (high/medium/low) on every result. Weighted average gives a baseline accuracy estimate.
2. **Pass 2** — 20-app re-research sample (biased toward low/medium confidence). Key fields (`auth_methods`, `self_serve`, `buildability`, `mcp_exists`) are compared between Pass 1 and Pass 2. Agreement rate = verified accuracy.
3. **Pass 3** — Human placeholder. `data/needs_human_check.json` lists the 10 apps most needing manual review, with `evidence_url` for each.

Full results in `data/verification_report.json`.

---

## Schema

Every app produces one `AppResearch` record (see `schema.py`):

```python
app_name, category, one_liner
auth_methods: list[str]          # OAuth2 / API Key / Bearer Token / etc.
self_serve: bool                  # can dev sign up without sales?
trial_available: bool
gating_note: str
api_type: str                     # REST / GraphQL / Both / gRPC / None
api_breadth: str                  # broad / moderate / narrow / none
mcp_exists: bool
mcp_url: Optional[str]
buildability: str                 # ready / needs_outreach / not_buildable / non_standard
blocker: Optional[str]
opportunity_score: int            # 1–5
evidence_url: str
confidence: str                   # high / medium / low
confidence_per_field: dict[str, str]
source: str                       # composio_native / web_search / deep_fetch / manual
tier_used: int                    # 1 / 2 / 3
run_timestamp: str
```
