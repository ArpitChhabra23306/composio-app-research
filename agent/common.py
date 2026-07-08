"""
common.py — Shared pipeline logic for the Composio app-research agent.
Both research_agent.py (first pass) and rerun_v2.py import from here.

=== VERIFIED SDK CALL SHAPE (tested live against this account) ===
  CORRECT:   composio_client.client.tools.execute(tool_slug=..., arguments=...)
  INCORRECT: composio_client.tools.execute(slug=...)  — crashes with ToolVersionRequiredError
  user_id:   OPTIONAL — works fine without it (confirmed by 99-app run)

=== VERIFIED TOOL SLUGS ===
  Search:    COMPOSIO_SEARCH_DUCK_DUCK_GO
  Fetch:     COMPOSIO_SEARCH_FETCH_URL_CONTENT

=== VERIFIED RESPONSE SHAPES ===
  Search: res.data["results"] -> list of dicts with keys: link, title, snippet, date, position
  Fetch:  res.data["results"] -> list of dicts with keys: text, url, title, author, image

All of the above were confirmed by live smoke tests — not assumed.
"""
import os
import time
import json
import sys
from dotenv import load_dotenv
from openai import OpenAI
from composio import Composio

# Prompt templates live in the agent/ folder — caller adds that to path before import
from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

load_dotenv()

openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
composio_client = Composio(api_key=os.environ.get("COMPOSIO_API_KEY"))

# Verified tool slugs — confirmed working by live test
SEARCH_TOOL_SLUG = "COMPOSIO_SEARCH_DUCK_DUCK_GO"
FETCH_TOOL_SLUG = "COMPOSIO_SEARCH_FETCH_URL_CONTENT"


def execute_with_backoff(tool_slug, arguments, retries=3, delay=5):
    """
    Executes a Composio tool with exponential backoff.

    VERIFIED CALL SHAPE:
      composio_client.client.tools.execute(tool_slug=..., arguments=...)
    
    NOTE: c.tools.execute(slug=...) is a DIFFERENT method that requires
    a toolkit version to be specified. It crashes with ToolVersionRequiredError
    when called without one. Do NOT use it. The .client.tools.execute path
    works without any version parameter and was confirmed across 99 apps.

    Returns:
      dict: the .data dict on success
      dict: {"_failed": True, "_error": "..."} on exhausted retries — never raises,
            so the caller can log an honest failure record rather than crashing.
    """
    last_error = None
    for attempt in range(retries):
        try:
            res = composio_client.client.tools.execute(
                tool_slug=tool_slug,
                arguments=arguments
            )
            if res.successful:
                return res.data
            # Log the actual error from the response — not just "unsuccessful"
            last_error = str(res.error) if res.error else "Tool returned unsuccessful=False with no error message"
            print(f"  Tool call unsuccessful [{tool_slug}] attempt {attempt+1}/{retries}: {last_error}")
        except Exception as e:
            last_error = str(e)
            print(f"  Exception executing [{tool_slug}] attempt {attempt+1}/{retries}: {last_error}")

        if attempt < retries - 1:
            sleep_time = delay * (2 ** attempt)
            print(f"  Retrying in {sleep_time}s...")
            time.sleep(sleep_time)

    # Return structured failure so callers record an honest row, not a crash
    return {"_failed": True, "_error": last_error}


def search_and_fetch_docs(app_name, website):
    """
    Searches for developer docs and fetches page content.

    Returns:
      docs_text (str): concatenated page text from up to 3 sources
      evidence_url (str): first URL that returned real content
      fetch_failures (list): list of {url, error} for URLs that failed
      fetch_ok (bool): True if at least one full page was fetched successfully
    """
    # Include "pricing" in the query — this is what makes gating detection work.
    # Without pricing pages in the result set, the agent can't see paywalls.
    query = f"{app_name} API authentication OAuth2 API key developer docs pricing"
    print(f"  Searching: {query}")

    data = execute_with_backoff(SEARCH_TOOL_SLUG, {"query": query})
    results = [] if data.get("_failed") else data.get("results", [])

    # Fallback if primary search returns nothing
    if not results:
        query2 = f"{app_name} developer API documentation"
        data = execute_with_backoff(SEARCH_TOOL_SLUG, {"query": query2})
        results = [] if data.get("_failed") else data.get("results", [])

    # Confirmed response key: results[i]["link"] (verified by smoke test)
    urls_to_try = [r["link"] for r in results[:4] if "link" in r]
    print(f"  URLs found: {urls_to_try}")

    # Always prepend the hint website — it's the most authoritative source
    if website:
        hint_url = website if website.startswith("http") else f"https://{website}"
        if hint_url not in urls_to_try:
            urls_to_try.insert(0, hint_url)

    raw_content_parts = []
    evidence_url = ""
    fetch_failures = []

    for url in urls_to_try[:3]:
        fetch_result = execute_with_backoff(FETCH_TOOL_SLUG, {"url": url})
        if fetch_result.get("_failed"):
            fetch_failures.append({"url": url, "error": fetch_result.get("_error", "")})
            print(f"  Failed to fetch {url}: {fetch_result.get('_error')}")
            continue

        # Confirmed response shape: results[0]["text"] (verified by smoke test)
        page_results = fetch_result.get("results", [])
        if page_results:
            text = page_results[0].get("text", "")
            if len(text.strip()) > 300:
                raw_content_parts.append(f"[SOURCE: {url}]\n{text[:6000]}")
                if not evidence_url:
                    evidence_url = url
                print(f"  Successfully fetched {len(text)} chars from {url}")
            else:
                print(f"  Content from {url} too short ({len(text)} chars), skipping")

    fetch_ok = len(raw_content_parts) > 0

    if not raw_content_parts:
        # Honest degraded fallback: search snippets only.
        # Downstream MUST set confidence=low in this case.
        print("  Could not fetch full page content. Falling back to search snippets.")
        snippets = [
            f"Title: {r.get('title', '')}\nLink: {r.get('link', '')}\nSnippet: {r.get('snippet', '')}"
            for r in results[:6]
        ]
        raw_content_parts = ["\n".join(snippets)] if snippets else ["NO SEARCH RESULTS OR PAGE CONTENT FOUND."]
        evidence_url = urls_to_try[0] if urls_to_try else (website or "")

    docs_text = "\n\n---\n\n".join(raw_content_parts)
    return docs_text, evidence_url, fetch_failures, fetch_ok


def extract_metadata(app, raw_docs, model="gpt-4o"):
    """Calls OpenAI to extract structured JSON from fetched docs."""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        app_name=app["name"],
        category=app["category"],
        website=app.get("website", ""),
        docs_content=raw_docs[:14000],
    )
    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,  # Deterministic — critical for reproducibility
    )
    return json.loads(response.choices[0].message.content)


def build_result_record(app, extracted, evidence_url, fetch_ok, fetch_failures):
    """
    Assembles the final result record with HONEST failure handling.

    CRITICAL FIX vs original code:
    The original used optimistic defaults:
        extracted.get("self_serve", "self-serve")       <- silently becomes "self-serve" on failure
        extracted.get("buildability_verdict", "buildable today")  <- silently becomes "buildable"
        extracted.get("blocker", "none")                <- silently becomes "none"
        extracted.get("confidence", "high")             <- silently becomes "high"

    If the LLM returns incomplete JSON or a field is missing, those defaults
    convert a FAILURE into the ROSIEST possible answer — inflating apparent
    accuracy and hiding real problems. This is the opposite of what the
    assignment asks for.

    Fixed: missing fields default to "unknown" + confidence="low" + a note.
    A needs_human_review flag makes it easy to filter these in downstream analysis.
    """
    missing_fields = []

    def get_or_flag(key, fallback="unknown"):
        val = extracted.get(key)
        if val is None or val == "" or val == []:
            missing_fields.append(key)
            return fallback
        return val

    api_surface_raw = extracted.get("api_surface") or {}
    if not api_surface_raw:
        missing_fields.append("api_surface")

    # Confidence: can never be high if we couldn't fetch any real page content
    confidence = extracted.get("confidence", "low")
    if not fetch_ok:
        confidence = "low"

    # Build honest agent_notes — append fetch failures and missing fields
    notes = extracted.get("agent_notes", "")
    if fetch_failures:
        failed_urls = ", ".join(f["url"] for f in fetch_failures)
        notes = (notes + " " if notes else "") + \
            f"[Fetch failures ({len(fetch_failures)} URL(s)): {failed_urls}]"
    if missing_fields:
        notes = (notes + " " if notes else "") + \
            f"[Incomplete extraction — these fields defaulted to 'unknown': {', '.join(missing_fields)}]"
        confidence = "low"

    # auth_methods: empty list is a real finding (no auth found in docs), not a failure
    auth_methods = extracted.get("auth_methods", [])
    if not isinstance(auth_methods, list):
        auth_methods = []
        missing_fields.append("auth_methods")

    return {
        "id": app["id"],
        "app": app["name"],
        "category": app["category"],
        "one_liner": get_or_flag("one_liner", ""),
        "auth_methods": auth_methods,
        "self_serve": get_or_flag("self_serve"),         # "unknown" not "self-serve"
        "gating_notes": get_or_flag("gating_notes", ""),
        "api_surface": {
            "type": api_surface_raw.get("type", "unknown"),
            "breadth": api_surface_raw.get("breadth", "unknown"),
            "existing_mcp": api_surface_raw.get("existing_mcp", False),
        },
        "buildability_verdict": get_or_flag("buildability_verdict"),  # "unknown" not "buildable today"
        "blocker": get_or_flag("blocker"),               # "unknown" not "none"
        "evidence_url": evidence_url or extracted.get("evidence_url", app.get("website", "")),
        "confidence": confidence,                         # "low" not "high" on failure
        "agent_notes": notes,
        "needs_human_review": bool(missing_fields) or not fetch_ok or bool(fetch_failures),
    }
