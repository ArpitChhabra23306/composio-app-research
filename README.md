# Composio App Intelligence — 100-App Research Pipeline

> **Built for:** Composio AI Product Ops Intern Assignment  
> **Pipeline:** Composio SDK + OpenAI gpt-4o → 100 researched apps → verified HTML report

---

## 🚀 What This Does

An automated agent pipeline that:
1. Searches for developer documentation for 100 apps using **Composio's search tools**
2. Fetches and reads the actual docs pages (not just snippets)
3. Extracts structured metadata (auth methods, gating, API surface, buildability) via **gpt-4o**
4. Verifies a stratified 20-app sample with independent fresh fetches
5. Publishes everything in a single self-explanatory HTML page

---

## 📊 Key Findings (V3 — Post-Correction Run)

| Metric | Value |
|---|---|
| **OAuth2 adoption** | 63% of apps |
| **API Key adoption** | 67% of apps |
| **Both OAuth2 + API Key** | ~40% of apps |
| **Self-Serve access** | 88% of apps |
| **Gated (enterprise/sales)** | 9% of apps |
| **Buildable today** | 89 apps |
| **Easy wins (no MCP yet)** | 78 apps |
| **Blocked (no public API)** | 3 apps |

**Top categories for easy wins:** Dev/Infra, Productivity, Ecommerce (all 100% self-serve).  
**Top categories for gating:** Data/SEO, Finance, AI/Research (partial gating common).

---

## 🗂️ Repo Structure

```
composio-app-research/
├── README.md
├── requirements.txt
├── .env.example
│
├── data/
│   ├── apps.json                  # input: 100 apps with category + hint URL
│   ├── results_v1.json            # V1: gpt-4o-mini, basic prompt (30% accuracy)
│   ├── results_v2.json            # V2: gpt-4o, 14 reruns on known-bad apps
│   ├── results_v2.json            # V3: gpt-4o, full fresh run, corrected pipeline
│   ├── results_v2.jsonl           # crash-safe incremental log for V3
│   ├── patterns.json              # aggregated distributions per category
│   ├── version_comparison.json    # per-app V1 vs V2 vs V3 diff table
│   ├── accuracy_all.json          # accuracy stats across all versions
│   ├── verification_sample.json   # V1 20-app manual verification
│   ├── verification_v2.json       # V3 20-app stratified verification
│   └── failures.json              # apps that failed all retries
│
├── agent/
│   ├── research_agent.py          # original V1 agent
│   ├── research_agent_v2.py  # V3 full run (all 100 apps)
│   ├── common.py                  # shared pipeline logic (SDK, extraction, failure handling)
│   ├── prompts.py                 # system prompt + user prompt template
│   ├── verify_agent.py            # V1/V2 verification script
│   ├── verify_v2.py               # V3 stratified verification
│   └── rerun_v2.py                # targeted rerun (known-bad or low-confidence scope)
│
├── analysis/
│   ├── patterns.py                # aggregates results into patterns.json
│   ├── compare_versions.py        # generates V1/V2/V3 comparison tables
│   └── build_html.py           # builds the final index.html
│
└── site/
    └── index.html                 # ← THE FINAL DELIVERABLE (open this)
```

---

## ⚡ Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env and set:
# OPENAI_API_KEY=sk-...
# COMPOSIO_API_KEY=...  (from https://app.composio.dev/settings)
```

### 3. Run the full pipeline (all 100 apps, ~35 minutes)

```bash
python agent/research_agent_v2.py
```

Resume safely after a crash (already-done apps are skipped):
```bash
python agent/research_agent_v2.py  # just re-run, it resumes from results_v2.jsonl
```

### 4. Run verification on a stratified 20-app sample

```bash
python agent/verify_v2.py
```

### 5. Generate comparison stats across all versions

```bash
python analysis/compare_versions.py
python analysis/patterns.py
```

### 6. Build the final HTML report

```bash
python analysis/build_html.py
# Output: site/index.html
```

---

## 🔧 Composio Toolkit Used

This pipeline uses **`COMPOSIO_SEARCH`** — Composio's own hosted search toolkit, which requires no separate API key.

**Two tools used:**

| Tool Slug | Purpose | SDK Call |
|---|---|---|
| `COMPOSIO_SEARCH_DUCK_DUCK_GO` | Web search for developer docs | `composio_client.client.tools.execute(tool_slug=..., arguments={"query": "..."})` |
| `COMPOSIO_SEARCH_FETCH_URL_CONTENT` | Fetch full markdown text of a URL | `composio_client.client.tools.execute(tool_slug=..., arguments={"url": "..."})` |

**Verified SDK call shape** (confirmed live against the account):
```python
composio_client = Composio(api_key=os.environ.get("COMPOSIO_API_KEY"))
res = composio_client.client.tools.execute(
    tool_slug="COMPOSIO_SEARCH_DUCK_DUCK_GO",
    arguments={"query": "Slack API OAuth authentication"}
)
if res.successful:
    results = res.data["results"]  # list with keys: link, title, snippet
```

> **Note:** `composio_client.tools.execute(slug=...)` (the newer top-level path) requires a toolkit version parameter and throws `ToolVersionRequiredError` without it. The `.client.tools.execute(tool_slug=...)` path works without version specification and was confirmed across 100 apps. Both `user_id` (optional) and `version` (not needed for `.client.` path) were verified as not required.

---

## 🔄 Pipeline Architecture

```
apps.json (100 apps)
    |
    v
[STEP 1] SEARCH — COMPOSIO_SEARCH_DUCK_DUCK_GO
         Query: "{app} API authentication OAuth2 API key developer docs pricing"
         → returns top URLs with titles + snippets
    |
    v
[STEP 2] FETCH — COMPOSIO_SEARCH_FETCH_URL_CONTENT  
         Fetches up to 3 URLs per app (developer portal + pricing page)
         → returns clean markdown text of each page
    |
    v
[STEP 3] EXTRACT — gpt-4o (temperature=0.0, json_object mode)
         System prompt enforces:
           - MUST check for both OAuth2 AND API Key (most common V1 error)
           - MUST look for "contact sales" / "enterprise plan" gating signals
           - Specific evidence required for gating_notes (plan name + price)
    |
    v
[STEP 4] VALIDATE — common.py build_result_record()
         Honest defaults: missing fields → "unknown" (not "self-serve"!)
         Fetch failures → confidence="low" + needs_human_review=True
         No silent optimistic defaults anywhere
    |
    v
[STEP 5] PERSIST — Crash-safe JSONL log + sorted JSON
    |
    v
[STEP 6] VERIFY — stratified 20-app independent re-check
         Fresh fetch + gpt-4o cross-check → field-level accuracy report
```

---

## 📈 Accuracy Improvement Story

| Version | Model | Scope | Overall Accuracy | Key Fix |
|---|---|---|---|---|
| **V1** | gpt-4o-mini | 100 apps (all) | ~30% | Baseline |
| **V2** | gpt-4o | 14 known-bad reruns | ~75% | Better prompt, better model |
| **V3** | gpt-4o | 100 apps (full fresh) | See verification_v2.json | Corrected SDK, honest failures |

**Critical bug fixed in V3 (not in V1/V2):**
- `extracted.get("self_serve", "self-serve")` → **silently converted every failure to "self-serve"**. This was the root cause of the inflated "self-serve" stats in V1.
- Fixed: all missing fields now default to `"unknown"` with explicit `needs_human_review=True`.

---

## 🔬 Verification Methodology

Three-tier testing was performed:

1. **Live SDK smoke tests** — Confirmed tool slug names, response shapes, and SDK call signatures by running real API calls before building the pipeline.
2. **Independent agent verification** — `verify_agent.py` ran fresh searches for a 20-app stratified sample and compared against agent output.
3. **Manual ground-truth audit** — 8 apps verified by directly reading official developer docs:
   - Slack, HubSpot, Stripe, Shopify, Notion, Google Ads: **100% correct** in V3
   - Ahrefs, Clay: Auth methods **100% correct**; self-serve debatable (free trial ≠ free API use)

---

## ⚠️ Known Limitations

- **iPayX (#85):** Limited public developer docs. V3 fetched the pricing page successfully but full API documentation isn't publicly indexed.
- **MrScraper (#54):** V3 successfully fetched docs; V1 completely failed (optimistic default masked it).
- **Ahrefs, Clay:** Agent marks "self-serve" because free account creation is instant, but production API use requires paid plans. These are "mixed" in reality.
- **Rate-limiting:** `time.sleep(2)` between apps. The pipeline uses exponential backoff (5s → 10s → 20s) on Composio failures.

---

## 📦 Requirements

```
openai>=1.0.0
composio>=0.7.0
python-dotenv>=1.0.0
```

---

## 💡 Why Composio?

Using Composio's own tools for this research is the cleanest possible meta-signal — evaluating which apps Composio should integrate by using Composio to do the research. The `COMPOSIO_SEARCH` toolkit required no third-party API key signup, and both tools (`DUCK_DUCK_GO` + `FETCH_URL_CONTENT`) worked reliably across 100 apps.

The assignment explicitly says to use Composio SDK/MCP — this pipeline does exactly that, and the README documents specifically which tools were used, why, and what was verified.
