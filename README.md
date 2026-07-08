# Composio App Intelligence — 100-App Research Pipeline

> **Built for:** Composio AI Product Ops Intern Assignment  
> **Pipeline:** Composio SDK + OpenAI gpt-4o → 100 researched apps → verified HTML report

---

## 🚀 Overview & The Deliverable

This repository contains an automated agent pipeline designed to research developer documentation for 100 applications. The goal is to determine authentication methods, gating status (self-serve vs. partnership required), API surface breadth, and buildability (whether an MCP server can be built today).

**The Final Deliverable** is a single, self-explanatory HTML file located at `site/index.html`. It contains:
- A filterable, sortable matrix of all 100 apps.
- A summary of patterns and trends (auth dominance, gating status, easy wins).
- A breakdown of the pipeline's architecture and the Composio SDK tools used.
- Honest verification results comparing the agent's output against human ground truth.

---

## 📊 Key Findings & Patterns (V2 — Final Corrected Run)

From our pipeline's extraction of all 100 apps:

| Metric | Result |
|---|---|
| **OAuth2 Adoption** | 71% of apps |
| **API Key Adoption** | 64% of apps |
| **Both OAuth2 + API Key** | 42% of apps |
| **Self-Serve Access** | 80 apps |
| **Gated (Enterprise/Partnership)** | 12 apps |
| **Mixed (Free tier + paid API)** | 8 apps |
| **Buildable Today** | 80 apps |
| **Easy Wins (No existing MCP, self-serve, broad API)** | 71 apps |
| **Blocked (No public API / strict partnership)** | 11 apps |

**Top categories for easy wins:** Dev/Infra, Productivity, and Ecommerce (almost entirely self-serve).  
**Top categories for gating:** Data/SEO, Finance, and AI/Research (partnership requirements are common).

---

## ⚙️ How the Pipeline Works

Doing this by hand does not scale. We built an automated pipeline using the **Composio SDK** to perform the research:

1. **Search (Composio SDK):** The agent uses `composio_client.client.tools.execute(tool_slug="COMPOSIO_SEARCH_DUCK_DUCK_GO")` to query duckduckgo for `{app} API authentication developer docs`.
2. **Fetch (Composio SDK):** The agent uses `tool_slug="COMPOSIO_SEARCH_FETCH_URL_CONTENT"` to scrape the actual text content of the top developer documentation links.
3. **Extraction (LLM):** `gpt-4o` (temperature=0) processes the markdown using a strict JSON schema. It scans for gating phrases ("contact sales", "enterprise only") and auth types.
4. **Honest Failure Handling:** If an app defeats the scraper, the pipeline does not hallucinate a "self-serve" default. It outputs "unknown" and flags `needs_human_review=True`.
5. **Report Generation:** A Python script compiles the JSON records into the final HTML view.

---

## 🔍 Verification & Accuracy

Accuracy is what matters most. We implemented a rigorous verification loop. 

### The Evolution: V1 vs V2
* **V1 (gpt-4o-mini):** Initially had a ~60% auth accuracy and a strong bias towards assuming every app was "self-serve" if it couldn't find the pricing page. It also frequently stopped reading after finding the first auth method, missing secondary ones.
* **V2 (gpt-4o):** We upgraded the model, fixed the default behaviors to be brutally honest (flagging unknowns), and improved the search prompting. **63 apps changed classification between V1 and V2.**

### Manual Ground Truth Verification
To prove trustworthiness, we took a stratified 11-app sample (mixing high-confidence, known-bad, and varying categories) and performed manual human verification directly against the developer docs:

- **Self-serve classification accuracy:** **100%** (11/11)
- **Auth methods accuracy:** **72.7%** (8/11)

**Why the 3 auth misses?** We honestly documented them in the HTML report. In all 3 cases, the agent found the *Product's* auth (e.g., Supabase Auth OAuth provider) rather than the *API's* auth (Supabase API keys). This highlights the need for secondary "API vs Product auth" prompts in future iterations.

---

## 🗂️ Repository Structure

```text
composio-app-research/
├── README.md
├── requirements.txt
├── .env.example
│
├── data/
│   ├── apps.json                  # Input: 100 apps with category + hint URL
│   ├── results_v1.json            # V1: baseline (gpt-4o-mini, flawed defaults)
│   ├── results_v2.json            # V2: final corrected run (gpt-4o, honest defaults)
│   ├── results_v2.jsonl           # Incremental crash-safe log for V2
│   ├── patterns.json              # Aggregated distributions for the HTML report
│   ├── version_comparison.json    # V1 vs V2 per-app diff table
│   ├── verification_manual_v2.json# Human-verified GT results
│   └── verification_v2.json       # Automated verification results
│
├── agent/
│   ├── research_agent_v2.py       # The main V2 run script
│   ├── common.py                  # Shared pipeline logic (Composio SDK, extraction)
│   ├── prompts.py                 # System and user prompt templates
│   ├── verify_v2.py               # Automated verification script
│   └── manual_ground_truth.py     # Script to compute manual GT accuracy
│
├── analysis/
│   ├── patterns.py                # Aggregates V2 results into patterns.json
│   ├── compare_versions.py        # Compares V1 vs V2 to measure pipeline improvement
│   └── build_html.py              # Compiles the data into the final HTML deliverable
│
└── site/
    └── index.html                 # ← THE FINAL DELIVERABLE. Open in any browser.
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
# COMPOSIO_API_KEY=...  (Get this from https://app.composio.dev/settings)
```

### 3. Run the research agent (Optional)
If you want to re-run the research from scratch (takes ~30 mins):
```bash
python agent/research_agent_v2.py
```

#### 4. Build and view the HTML report
To generate the final HTML page from the JSON data:
```bash
python analysis/build_html.py
```

**To view the report**, you can start a local server to view it in your browser without file-path issues:
```bash
python -m http.server 8080 --directory site
```
Then open your browser to: [http://localhost:8080](http://localhost:8080)

*(Alternatively, you can just double-click the `site/index.html` file in your File Explorer, or use `start site\index.html` in Windows).*

---

*End of Document. Refer to `site/index.html` for the complete visual case study.*
