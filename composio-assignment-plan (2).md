# Composio AI Product Ops Intern Assignment — Execution Plan

## Goal (one sentence)
Build an agent pipeline (using Composio's SDK/MCP) that researches 100 apps for auth/gating/API-surface/buildability, verify a sample by hand, iterate until accuracy is high, then present everything on one self-explanatory HTML page.

## Non-negotiables from the brief (checklist to keep visible the whole time)
- [ ] 100 apps, each with: category + 1-line description, auth method(s), self-serve vs gated, API surface (REST/GraphQL, breadth, existing MCP?), buildability verdict + blocker, evidence URL
- [ ] Patterns section — stated up top, plainly, as the headline (not buried)
- [ ] Built with an agent/pipeline, not by hand — ideally Composio SDK + MCP
- [ ] Verification loop — sample cross-checked by hand, hits/misses shown honestly, accuracy improved v1 → v2 with evidence
- [ ] One HTML page, understandable in ~2 minutes, no narration needed
- [ ] Live deployed link + source repo + README
- [ ] Honesty about failures — gated apps or wrong answers are fine to show, hiding them is not

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  apps.json       │ --> │  Research Agent   │ --> │  results.json    │
│  (100 apps,      │     │  (Composio SDK/   │     │  (structured,    │
│  seeded list)    │     │  MCP + web search/│     │  per-app record) │
│                  │     │  browse tool)     │     │                  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                    ┌─────────────────────────────────────┤
                    │                                     │
             ┌──────▼───────┐                     ┌──────▼────────┐
             │ Verification  │                     │  Pattern       │
             │ Agent/Script  │                     │  Analysis      │
             │ (re-check     │                     │  script        │
             │ sample of ~20)│                     │  (aggregations)│
             └──────┬───────┘                     └──────┬────────┘
                    │                                     │
                    ▼                                     ▼
             accuracy_report.json                  patterns.json
                    │                                     │
                    └───────────────┬─────────────────────┘
                                    ▼
                          index.html (final deliverable)
```

### Why Composio SDK/MCP specifically (verified against current docs, July 2026)
Composio's own product lets an agent call tools through MCP or direct SDK function-calling. Using it here is literally "using their product to do their job" — a strong meta-signal for the interview. Concrete, verified facts to build against (don't assume older/guessed API shapes):

- **Packages**: Python `pip install composio` (needs Python 3.10+) or TypeScript `npm install @composio/core`. Pick Python for this — easier scripting/JSON handling for 100 rows.
- **Auth**: run `composio login` (interactive OAuth to your Composio account) once, then use an API key server-side. In code: `composio = Composio(api_key=...)`.
- **Toolkit choice — corrected**: there are two viable options and they are NOT equivalent in setup cost:
  - **`COMPOSIO_SEARCH` (recommended)**: Composio's own hosted search toolkit — **no separate API key or account needed**, it's free and auth-free by design. It bundles a general web-search tool (`COMPOSIO_SEARCH_WEB`) plus a page-content-extraction tool (Exa-backed under the hood) that pulls clean markdown text from a public URL — exactly the two-step "search → fetch full page" pattern this assignment needs. This is the lowest-friction choice and the cleanest "used Composio's own tooling" story for the interview.
  - **`TAVILY` or `EXA` as standalone toolkits**: these are third-party services connected *through* Composio, but **you must bring your own API key for each** — sign up separately at tavily.com or exa.ai, create a Composio auth config for that toolkit, and link it. Tavily/Exa have their own free tiers, so this is doable, but it's an extra signup step my earlier draft glossed over. Only worth it if `COMPOSIO_SEARCH`'s extraction tool proves too shallow for some docs pages during your smoke test.
- **Inspect tools before writing code** — this is faster than reading docs: `composio tools list --toolkit composio_search` and `composio tools info <TOOL_NAME>` show you the exact input/output schema for each candidate tool. Do this in Phase 0 instead of guessing tool names.
- **Pattern for pulling tools into an agent (Python SDK)**:
  ```python
  from composio import Composio
  composio = Composio(api_key="...")
  tools = composio.tools.get(user_id="research-agent", toolkits=["COMPOSIO_SEARCH"])
  # pass `tools` into your model's function-calling / tool-use loop
  # or call a specific tool directly:
  result = composio.tools.execute(
      "COMPOSIO_SEARCH_WEB", user_id="research-agent",
      arguments={"query": "Salesforce API developer authentication docs"}
  )
  ```
- **Sessions is now the officially recommended pattern** (current docs label plain `tools.get()`/`tools.execute()` as "Direct Tool Execution — Legacy"), though the legacy pattern above is still fully supported and shown throughout the SDK reference — either works, but if you want to match Composio's current recommended style: `session = composio.create(user_id, toolkits=["COMPOSIO_SEARCH"])`, then use `session.tools` / `session.mcp.url`. Mention in the README which pattern you picked and that you're aware of the newer session-based option — this heads off an obvious "why not sessions?" interview question.
- **Rate limits are per-tool, not one global number** — don't hardcode a single "60 req/min" assumption (that figure came from a general marketing page, not a tool-specific spec). Composio's own tool docs show examples like a documented ~2 requests/second limit with exponential backoff (1s → 2s → 4s) on 429s for at least one search tool. Check `composio tools info <TOOL_NAME>` for the specific tool's limit if shown, and build simple retry-with-backoff into the loop regardless — cheap insurance either way.
- **Verify during the Phase 0 smoke test whether the extraction tool accepts an arbitrary URL you supply** (e.g. feed it `developer.salesforce.com` directly) **or only URLs it discovered itself via search**. If it's search-result-only, your pipeline needs a search step before every fetch step (two tool calls per app minimum), which affects your pacing math.
- **If a toolkit call fails or an app has no clean docs**, that's a legitimate "blocker: no public API found" finding for that row — don't force a scraper workaround, since the brief explicitly says gated/undocumented apps are a valid finding.
- Document in the README exactly which Composio toolkit(s) you used and why — this is a natural interview question.

---

## Repo structure

```
composio-app-research/
├── README.md
├── data/
│   ├── apps.json              # input: the 100 apps + categories
│   ├── results_v1.json        # first pass agent output
│   ├── results_v2.json        # after verification-driven fixes
│   └── verification_sample.json  # the ~20 manually checked apps, with notes
├── agent/
│   ├── research_agent.py      # main pipeline: loops apps -> calls agent -> writes results
│   ├── prompts.py             # system prompt + per-field extraction prompt
│   └── verify_agent.py        # re-runs / cross-checks sample against fresh sources
├── analysis/
│   └── patterns.py            # aggregates results_v2.json into patterns.json
├── site/
│   └── index.html             # the final single-page deliverable
└── requirements.txt
```

---

## Phase-by-phase plan (target: 6–8 hours)

### Phase 0 — Setup (30 min)
- `pip install composio` (Python 3.10+ required). Run `composio login` once to authenticate the CLI/SDK to your account, then generate an API key from the dashboard.
- Inspect the toolkit before writing any code: `composio tools list --toolkit composio_search` then `composio tools info <TOOL_NAME>` on the search tool and the page-extraction tool. This tells you exact input/output schemas in under a minute — faster and more reliable than reading docs pages.
- Do a 1-app smoke test end-to-end (e.g. "GitHub"): search → extract page content → confirm you get real docs text back, not just a search snippet. Critically, test whether the extraction tool accepts a URL you supply directly or only URLs surfaced by its own search — this determines your per-app call count and pacing.
- Only fall back to connecting `TAVILY` or `EXA` as separate toolkits (which each need their own third-party API key/signup) if `COMPOSIO_SEARCH`'s extraction proves too shallow on a few sample docs pages.
- Create `data/apps.json` from the 100-app list already given in the brief (category, name, hint/URL). This is static — no need to research this part, it's provided.

### Phase 1 — Build the research agent (90–120 min)
Per-app pipeline, for each of the 100:
1. Agent takes app name + category + hint URL.
2. Tool call: web search "{app} API documentation authentication" + fetch the top docs URL (prefer the hint URL first, then search-verify).
3. Extraction prompt (see below) asks the model to output **strict JSON** with the required fields, each with a `confidence` (high/med/low) and `evidence_url`.
4. Write result to `results_v1.json` as you go (don't hold everything in memory only — persist incrementally, so a crash doesn't lose 80 apps of work).

**Extraction schema per app (this is your JSON contract):**
```json
{
  "id": 1,
  "app": "Salesforce",
  "category": "CRM and Sales",
  "one_liner": "...",
  "auth_methods": ["OAuth2"],
  "self_serve": "self-serve | gated | mixed",
  "gating_notes": "free dev/sandbox account available, no partnership needed",
  "api_surface": {
    "type": "REST",
    "breadth": "very broad (thousands of objects/endpoints)",
    "existing_mcp": true
  },
  "buildability_verdict": "buildable today",
  "blocker": "none | needs paid plan | needs partnership | no public API | auth complexity",
  "evidence_url": "https://developer.salesforce.com/...",
  "confidence": "high",
  "agent_notes": "free text: anything ambiguous or worth flagging"
}
```

**System prompt sketch for the extraction step** (put in `prompts.py`):
> "You are researching developer/API access for {app}, a {category} tool. Using the fetched docs content, output ONLY valid JSON matching this schema: [schema]. If information is unclear or you can't verify something, mark confidence as 'low' and say so in agent_notes rather than guessing. Do not fabricate URLs — evidence_url must be a URL you actually fetched or that appeared in search results."

This "don't fabricate, flag uncertainty" instruction matters a lot for your verification story later — it's what lets you say "the agent flagged X apps as low-confidence, and Y% of those turned out to be wrong, which is exactly why the flag is useful."

### Phase 2 — Run it across all 100 (30–60 min, mostly unattended)
- Run the loop **with backoff, not a hardcoded rate assumption**: build simple retry-with-exponential-backoff (e.g. 1s → 2s → 4s) on any 429/throttling response, since per-tool limits vary and aren't all published. This handles the pacing question safely regardless of the actual limit.
- Expect some apps to fail/timeout regardless (docs behind login, obscure tools like "Paygent Connect" or "fanbasis" that barely have public docs). Log failures explicitly to a `failures.json` — these are legitimate findings ("could not verify — no public docs found"), not bugs to hide.
- Spot-skim the raw output for anything obviously broken (empty fields, wrong app matched) before moving on.

### Phase 3 — Verification loop (60–90 min) — this is the highest-weighted part
1. Randomly sample ~15-20 apps (mix across categories and confidence levels — deliberately include some the agent marked low-confidence and some high-confidence, to test if the confidence signal itself is trustworthy).
2. **By hand**, open the real docs for each sampled app and check: auth method, self-serve vs gated, API surface, evidence URL validity.
3. Record in `verification_sample.json`: agent's answer vs your manual answer vs verdict (correct / partially correct / wrong), for each field.
4. Compute accuracy: e.g. "18/20 auth_method correct (90%), 14/20 self_serve correct (70%), 20/20 evidence_url resolved (100%)."
5. **Diagnose the failure pattern** — e.g., maybe the agent confuses "OAuth2" vs "API key" for apps that offer both, or overstates self-serve for apps that actually need admin approval. Fix the prompt (be more specific, add examples, force it to check for the specific phrase "contact sales" etc.).
6. **Re-run the failed/low-confidence subset** (not all 100 necessarily — re-running just the sample + any others sharing the same failure pattern is faster and still honest) → `results_v2.json`.
7. Re-check the same sample against v2 → show the accuracy delta, e.g. "self_serve accuracy: 70% → 90% after fixing the prompt to explicitly require finding sandbox/free-tier language."

This before/after number is the single most important thing on the page — it's literally what "verify your accuracy" is asking for.

### Phase 4 — Pattern analysis (30–45 min)
Compute and write into `patterns.json`:
- Auth method distribution (count/% OAuth2 vs API key vs Basic vs other) — overall and per category.
- Self-serve vs gated split — overall and per category (e.g., "Fintech and Ecommerce skew gated; Dev/Infra and Productivity skew self-serve").
- Most common blocker (tally the `blocker` field).
- "Easy wins" = self-serve + broad API + no existing MCP (buildable today, unclaimed).
- "Needs outreach" = gated + partnership/contact-sales blocker.
- Any category-level or auth-level correlation worth calling out (e.g., "every app requiring partnership approval also uses OAuth2 with restricted scopes" if that's true in your data).

### Phase 5 — Build the HTML page (90–120 min)
Single `index.html`, structured top-to-bottom exactly in this order (2-minute skim test):
1. **Headline patterns** (3-5 bullet/stat cards, big numbers, e.g. "62% OAuth2 · 41 self-serve / 59 gated · Top blocker: partnership required (23 apps)")
2. **Findings table/matrix** — all 100 apps, filterable/sortable if you have time (simple HTML/JS table with filter by category/gating/auth), each row linking to its evidence URL
3. **The agent** — short diagram or 3-4 sentence description of the pipeline (reuse the architecture diagram above, simplified), explicitly noting where a human stepped in
4. **Verification** — the accuracy table, v1 vs v2, honest hits/misses, 2-3 concrete examples of what was wrong and why
5. **Proof** — link/embed to the actual runnable script or a short recording/log of it running

Keep styling clean/minimal — this isn't a design test, but a cluttered page undercuts "understood in 2 minutes." Plain typography, a stats row, a table, done.

### Phase 6 — README + deploy (30 min)
README needs: what the tool does, exact run steps (`pip install composio`, `composio login`, set `COMPOSIO_API_KEY`, `python agent/research_agent.py`), which toolkit you used (`COMPOSIO_SEARCH` by default — no separate API key needed — or Tavily/Exa if you switched, and why), the backoff/retry strategy used, and known limitations (apps you couldn't verify, calls that failed, low-confidence flags).
Deploy `index.html` anywhere static (GitHub Pages, Vercel, Netlify) — pick whichever is fastest for you, doesn't need to be fancy infra.

---

## Time budget summary
| Phase | Time |
|---|---|
| Setup | 0.5h |
| Build agent | 1.5–2h |
| Run on 100 | 0.5–1h |
| Verification loop | 1–1.5h |
| Pattern analysis | 0.5–0.75h |
| HTML page | 1.5–2h |
| README + deploy | 0.5h |
| **Total** | **6–8h** |

## Things that will make this "perfect" rather than just complete
- The v1→v2 accuracy improvement is real and specific (not vague — actual numbers, actual example fixes).
- Failures are shown, not hidden (dead apps, gated apps, low-confidence flags all visible on the page).
- The confidence field is validated by the verification step (i.e., you prove low-confidence flags actually correlate with more errors — that's a nice signal that your agent isn't just guessing blind).
- Evidence URLs are real and clickable, not fabricated.
- The patterns are genuinely derived from the 100-row data (re-run the aggregation after v2, don't eyeball it).
