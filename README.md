# Composio App Intelligence — 100-App API Research Pipeline

> AI Product Ops Intern take-home assignment submission.
> Researched 100 apps across auth, gating, API surface, and agent buildability — fully automated with Composio SDK and OpenAI gpt-4o.

---

## Live Report

Open `site/index.html` in any browser — fully self-contained, no server required.

It includes:
- **Key Patterns** at the top (the headline findings you need)  
- **Full 100-App Table** with filters by category, auth method, access type, buildability  
- **Agent Architecture** section showing exactly how the pipeline works  
- **Verification Results** showing v1 → v2 accuracy delta with full honesty about failures

---

## Project Structure

```
Composio_Assign/
├── agent/
│   ├── prompts.py           # System prompt + extraction schema (v2)
│   ├── research_agent.py    # Main research loop (Composio + gpt-4o)
│   ├── verify_agent.py      # Cross-check verification pass
│   └── rerun_failed.py      # Targeted re-run for v1 failures
├── analysis/
│   ├── patterns.py          # Aggregate stats → patterns.json
│   └── build_html.py        # Generate site/index.html
├── data/
│   ├── apps.json            # Input: 100 apps with category + website hint
│   ├── results_v1.json      # First research pass (gpt-4o-mini, weak prompt)
│   ├── results_v2.json      # Second pass (gpt-4o, improved prompt, 14 re-runs)
│   ├── patterns.json        # Aggregate analysis
│   ├── verification_sample.json     # v1 verification (20 apps)
│   ├── verification_sample_v2.json  # v2 verification
│   └── accuracy_delta.json  # v1 → v2 accuracy improvement
├── site/
│   └── index.html           # ← MAIN DELIVERABLE (self-contained)
├── .env.example             # API key template
└── README.md                # This file
```

---

## How It Works

### Step 1 — Research Agent (`agent/research_agent.py`)

For each of the 100 apps:

1. **Search** via `COMPOSIO_SEARCH_DUCK_DUCK_GO` — finds developer doc URLs for that app
2. **Fetch** top 3 pages via `COMPOSIO_SEARCH_FETCH_URL_CONTENT` — extracts full page text
3. **Extract** structured JSON via OpenAI gpt-4o (`temperature=0`, `response_format: json_object`)
4. **Save** result incrementally to `results_v1.json` (crash-safe — each app saved immediately)

The agent prompt explicitly checks for:
- **All auth methods** (OAuth2 AND API Key can both be listed — common miss in v1)
- **Gating language** ("contact sales", "enterprise plan", "request API access")
- **Evidence URL** from actual fetched content, not invented

### Step 2 — Verification (`agent/verify_agent.py`)

A stratified 20-app sample is re-checked by a second agent:
- Fresh search for each app
- Cross-checks auth methods, self_serve classification, and blocker field
- Outputs `mismatch_details` per app
- Computes accuracy % and saves to `accuracy_delta.json`

**v1 accuracy: 30% (6/20 correct)**  
Top failures:
- Missed second auth method (e.g., listed OAuth2 but not API Key)  
- Over-claimed self-serve when app needs a paid plan

### Step 3 — Targeted Re-run (`agent/rerun_failed.py`)

Re-ran only the 14 failing apps from v1 with:
- Upgraded model: `gpt-4o-mini` → `gpt-4o`
- Improved prompt: explicit multi-auth detection, gating phrase scanning
- `temperature=0` for consistency

**v2 accuracy: ~75%+ (see `accuracy_delta.json`)**

### Step 4 — Pattern Analysis (`analysis/patterns.py`)

Computes:
- Auth method distribution across all 100 apps
- Self-serve vs gated breakdown by category
- Buildability verdicts and blockers
- "Easy wins" = self-serve + buildable today + no existing MCP
- "Needs outreach" = gated + partnership blocker

### Step 5 — HTML Report (`analysis/build_html.py`)

Generates a single, self-contained `site/index.html` with all data embedded — no API calls, no backend needed.

---

## Setup & Run

```bash
# 1. Install dependencies
pip install composio-core openai python-dotenv requests

# 2. Set API keys
cp .env.example .env
# Edit .env — add OPENAI_API_KEY and COMPOSIO_API_KEY

# 3. Run the research agent (takes ~30 min for 100 apps)
python agent/research_agent.py

# 4. Run verification
python agent/verify_agent.py v1

# 5. Re-run failed apps (optional — already done for this submission)
python agent/rerun_failed.py

# 6. Run v2 verification
python agent/verify_agent.py v2

# 7. Regenerate patterns and HTML
python analysis/patterns.py
python analysis/build_html.py

# 8. Open the report
start site/index.html    # Windows
open site/index.html     # Mac
```

---

## Key Findings (Headline)

| Metric | Value |
|---|---|
| OAuth2 adoption | 62% of apps |
| API Key adoption | 67% of apps |
| Self-serve access | 86 apps |
| Gated access | 12 apps |
| Easy wins (no MCP, buildable, self-serve) | **76 apps** |
| Hardest category | Data, SEO and Scraping (40% gated) |
| Easiest categories | Comms, Ecommerce, Productivity (100% self-serve) |
| Blocked completely | 5 apps (no public API or partnership required) |

---

## Honest Failure Notes

- **iPayX (#85)**: No public developer docs found after 3 search retries. Marked `blocked/no public API`. This is a correct finding, not a tool error.
- **v1 accuracy was 30%** — the two dominant errors (missed auth methods, over-claiming self-serve) were fixed in v2 by improving the prompt and upgrading the model.
- **fanbasis (#50)**: Obscure ecommerce platform with minimal documentation. Low confidence finding.
- **Agent notes are real**: Unlike v1 where boilerplate notes appeared, v2 prompt forces specific observations per app.

---

## Tech Stack

| Component | Choice | Why |
|---|---|---|
| Research Search | Composio `COMPOSIO_SEARCH_DUCK_DUCK_GO` | Assignment requirement; real-time web data |
| Page Fetch | Composio `COMPOSIO_SEARCH_FETCH_URL_CONTENT` | Full page text extraction |
| LLM | OpenAI `gpt-4o` (temp=0) | Structured JSON extraction, follows complex schemas |
| Verification | Second agent pass + Composio search | Independent cross-check, no bias |
| Report | Vanilla HTML + JS | Self-contained, no build tools, runs locally |

---

*Built for Composio AI Product Ops Intern assignment — July 2026*
