"""
rerun_failed.py — Re-runs only the 14 apps that failed verification in v1.
Reads results_v1.json, replaces failed entries, writes results_v2.json.
Uses improved prompt (prompts.py v2) and gpt-4o.
"""
import os
import json
import time
import traceback
import sys
from dotenv import load_dotenv
from openai import OpenAI
from composio import Composio

# Add agent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_FILE = os.path.join(BASE_DIR, "data", "apps.json")
RESULTS_V1_FILE = os.path.join(BASE_DIR, "data", "results_v1.json")
RESULTS_V2_FILE = os.path.join(BASE_DIR, "data", "results_v2.json")
VERIFICATION_FILE = os.path.join(BASE_DIR, "data", "verification_sample.json")

# The 14 app IDs that failed v1 verification
FAILED_IDS = {1, 4, 7, 11, 31, 37, 41, 50, 53, 60, 65, 81, 90, 92}

openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
composio_client = Composio(api_key=os.environ.get("COMPOSIO_API_KEY"))


def execute_with_backoff(tool_slug, arguments, retries=3, delay=5):
    for attempt in range(retries):
        try:
            res = composio_client.client.tools.execute(tool_slug=tool_slug, arguments=arguments)
            if res.successful:
                return res.data
        except Exception as e:
            print(f"  Error calling {tool_slug} (attempt {attempt+1}/{retries}): {e}")
        if attempt < retries - 1:
            time.sleep(delay * (2 ** attempt))
    raise Exception(f"Failed to execute {tool_slug} after {retries} attempts.")


def search_and_fetch_docs(app_name, website):
    """Search for docs and fetch the most relevant page content."""
    # Use a more targeted search that explicitly looks for auth methods and pricing
    query = f"{app_name} API authentication OAuth2 API key developer docs pricing"
    print(f"  Searching: {query}")

    data = execute_with_backoff("COMPOSIO_SEARCH_DUCK_DUCK_GO", {"query": query})
    results = data.get("results", [])

    if not results:
        query2 = f"{app_name} developer API documentation"
        data = execute_with_backoff("COMPOSIO_SEARCH_DUCK_DUCK_GO", {"query": query2})
        results = data.get("results", [])

    urls_to_try = [r["link"] for r in results[:4]]
    print(f"  URLs found: {urls_to_try}")

    # Also explicitly add the hint website
    if website and website not in urls_to_try:
        urls_to_try.insert(0, f"https://{website}" if not website.startswith("http") else website)

    raw_content_parts = []
    evidence_url = ""

    for url in urls_to_try[:3]:
        try:
            res = composio_client.client.tools.execute(
                tool_slug="COMPOSIO_SEARCH_FETCH_URL_CONTENT",
                arguments={"url": url}
            )
            if res.successful:
                page_results = res.data.get("results", [])
                if page_results:
                    text = page_results[0].get("text", "")
                    if len(text.strip()) > 300:
                        raw_content_parts.append(f"[SOURCE: {url}]\n{text[:6000]}")
                        if not evidence_url:
                            evidence_url = url
                        print(f"  Fetched {len(text)} chars from {url}")
        except Exception as e:
            print(f"  Failed to fetch {url}: {e}")

    if not raw_content_parts:
        # Fallback to search snippets
        snippets = [f"Title: {r['title']}\nLink: {r['link']}\nSnippet: {r['snippet']}" for r in results[:6]]
        raw_content_parts = ["\n".join(snippets)]
        evidence_url = urls_to_try[0] if urls_to_try else website

    return "\n\n---\n\n".join(raw_content_parts), evidence_url


def extract_metadata(app, raw_docs):
    user_prompt = USER_PROMPT_TEMPLATE.format(
        app_name=app["name"],
        category=app["category"],
        website=app["website"],
        docs_content=raw_docs[:14000]
    )
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.0  # zero temp for maximum consistency
    )
    return json.loads(response.choices[0].message.content)


def main():
    apps = json.load(open(APPS_FILE, encoding="utf-8"))
    results_v1 = json.load(open(RESULTS_V1_FILE, encoding="utf-8"))

    # Build lookup by ID
    v1_by_id = {r["id"]: r for r in results_v1}
    apps_by_id = {a["id"]: a for a in apps}

    print(f"Re-running {len(FAILED_IDS)} apps that failed v1 verification...")
    print(f"App IDs to re-run: {sorted(FAILED_IDS)}\n")

    updated_results = dict(v1_by_id)  # start with all v1 results

    for app_id in sorted(FAILED_IDS):
        app = apps_by_id.get(app_id)
        if not app:
            print(f"WARNING: App ID {app_id} not found in apps.json")
            continue

        print(f"\n{'='*50}")
        print(f"Re-running App #{app_id}: {app['name']} ({app['category']})")
        print(f"{'='*50}")

        try:
            raw_docs, evidence_url = search_and_fetch_docs(app["name"], app["website"])

            extracted = extract_metadata(app, raw_docs)

            result = {
                "id": app["id"],
                "app": app["name"],
                "category": app["category"],
                "one_liner": extracted.get("one_liner", ""),
                "auth_methods": extracted.get("auth_methods", []),
                "self_serve": extracted.get("self_serve", "self-serve"),
                "gating_notes": extracted.get("gating_notes", ""),
                "api_surface": {
                    "type": extracted.get("api_surface", {}).get("type", "REST"),
                    "breadth": extracted.get("api_surface", {}).get("breadth", "moderate"),
                    "existing_mcp": extracted.get("api_surface", {}).get("existing_mcp", False)
                },
                "buildability_verdict": extracted.get("buildability_verdict", "buildable today"),
                "blocker": extracted.get("blocker", "none"),
                "evidence_url": evidence_url or extracted.get("evidence_url", app["website"]),
                "confidence": extracted.get("confidence", "high"),
                "agent_notes": extracted.get("agent_notes", ""),
                "v2_rerun": True  # flag to show this was re-processed
            }

            updated_results[app_id] = result
            print(f"  -> auth: {result['auth_methods']} | self_serve: {result['self_serve']} | blocker: {result['blocker']} | confidence: {result['confidence']}")

            time.sleep(3)

        except Exception as e:
            print(f"  ERROR re-running {app['name']}: {e}")
            traceback.print_exc()

    # Write v2 results sorted by ID
    v2_results = sorted(updated_results.values(), key=lambda x: x["id"])
    with open(RESULTS_V2_FILE, "w", encoding="utf-8") as f:
        json.dump(v2_results, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"v2 results written: {len(v2_results)} apps total")
    print(f"Re-ran: {len(FAILED_IDS)} apps | Kept from v1: {len(v2_results) - len(FAILED_IDS)} apps")


if __name__ == "__main__":
    main()
