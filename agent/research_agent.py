import os
import json
import time
import traceback
from dotenv import load_dotenv
from openai import OpenAI
from composio import Composio
from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

load_dotenv()

# Setup paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_FILE = os.path.join(BASE_DIR, "data", "apps.json")
RESULTS_FILE = os.path.join(BASE_DIR, "data", "results_v1.json")
FAILURES_FILE = os.path.join(BASE_DIR, "data", "failures.json")

# Ensure directories exist
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)

# Initialize API clients
openai_api_key = os.environ.get("OPENAI_API_KEY")
composio_api_key = os.environ.get("COMPOSIO_API_KEY")

if not openai_api_key or not composio_api_key:
    print("WARNING: Please ensure OPENAI_API_KEY and COMPOSIO_API_KEY are set in your .env file.")

openai_client = OpenAI(api_key=openai_api_key)
composio_client = Composio(api_key=composio_api_key)

def load_json_file(file_path, default=None):
    if default is None:
        default = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            print(f"Error reading {file_path}, starting fresh.")
    return default

def save_json_file(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def execute_with_backoff(tool_slug, arguments, retries=3, delay=5):
    """Executes a Composio tool with exponential backoff on errors."""
    for attempt in range(retries):
        try:
            res = composio_client.client.tools.execute(tool_slug=tool_slug, arguments=arguments)
            if res.successful:
                return res.data
            else:
                print(f"Composio execution failed: {res.error}")
        except Exception as e:
            print(f"Error calling {tool_slug} (attempt {attempt+1}/{retries}): {e}")
        
        if attempt < retries - 1:
            sleep_time = delay * (2 ** attempt)
            print(f"Sleeping {sleep_time}s before retrying...")
            time.sleep(sleep_time)
            
    raise Exception(f"Failed to execute tool {tool_slug} after {retries} attempts.")

def search_docs(app_name, website):
    """Searches for developer authentication docs for the app."""
    # Build a query using the name and the developer portal URL hints
    query = f"{app_name} API developer documentation authentication"
    if website:
        # Use the website/hint URL domain to narrow down search
        domain = website.replace("https://", "").replace("http://", "").split("/")[0]
        query += f" site:{domain} OR {website}"
    
    print(f"Searching: {query}")
    data = execute_with_backoff(
        tool_slug="COMPOSIO_SEARCH_DUCK_DUCK_GO",
        arguments={"query": query}
    )
    
    results = data.get("results", [])
    return results

def fetch_url(url):
    """Fetches the markdown content of a URL."""
    print(f"Fetching URL: {url}")
    data = execute_with_backoff(
        tool_slug="COMPOSIO_SEARCH_FETCH_URL_CONTENT",
        arguments={"url": url}
    )
    results = data.get("results", [])
    if results:
        return results[0].get("text", "")
    return ""

def extract_metadata(app, raw_docs):
    """Uses OpenAI to extract structured JSON from the developer documentation."""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        app_name=app["name"],
        category=app["category"],
        website=app["website"],
        docs_content=raw_docs[:12000] # Limit content size to fit in context window
    )
    
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )
    
    extracted_text = response.choices[0].message.content
    extracted_json = json.loads(extracted_text)
    return extracted_json

def process_app(app):
    """Performs the full research pipeline for a single app."""
    print(f"\n==================================================")
    print(f"Processing App #{app['id']}: {app['name']} ({app['category']})")
    print(f"==================================================")
    
    # 1. Search for docs URLs
    search_results = search_docs(app["name"], app["website"])
    
    if not search_results:
        # Try a broader search without site domain if no results
        print("No search results with site filter. Trying broad search...")
        search_results = search_docs(app["name"], "")
        
    if not search_results:
        raise Exception("No search results found.")
        
    # 2. Pick top URLs and fetch contents
    urls_to_try = [r["link"] for r in search_results[:3]]
    print(f"URLs found: {urls_to_try}")
    
    raw_content = ""
    evidence_url = ""
    
    # Try fetching URLs in order until we get a meaningful page
    for url in urls_to_try:
        try:
            content = fetch_url(url)
            # If content is non-empty and long enough, we accept it
            if len(content.strip()) > 300:
                raw_content = content
                evidence_url = url
                print(f"Successfully fetched content from {url} ({len(content)} chars)")
                break
            else:
                print(f"Content from {url} is too short ({len(content)} chars). Trying next URL...")
        except Exception as e:
            print(f"Failed to fetch content from {url}: {e}")
            
    if not raw_content:
        # Fall back to using search snippets if we couldn't fetch any full page
        print("Could not fetch full page content. Falling back to search snippets.")
        snippets = []
        for r in search_results[:5]:
            snippets.append(f"Title: {r['title']}\nLink: {r['link']}\nSnippet: {r['snippet']}\n")
        raw_content = "\n".join(snippets)
        evidence_url = urls_to_try[0] if urls_to_try else app["website"]
        
    # 3. Extract JSON metadata using OpenAI
    extracted = extract_metadata(app, raw_content)
    
    # Clean up and ensure required schema format matches
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
        "agent_notes": extracted.get("agent_notes", "")
    }
    
    return result

def main(batch_size=None):
    # Load input apps
    apps = load_json_file(APPS_FILE)
    if not apps:
        print("No apps found in apps.json.")
        return
        
    # Filter if batch size is specified (e.g. for testing)
    if batch_size:
        apps = apps[:batch_size]
        print(f"Running batch of {batch_size} apps.")
        
    # Load existing results to allow resuming
    results = load_json_file(RESULTS_FILE)
    failures = load_json_file(FAILURES_FILE)
    
    processed_ids = {r["id"] for r in results}
    failed_ids = {f["id"] for f in failures}
    
    print(f"Already processed: {len(processed_ids)} apps. Already failed: {len(failed_ids)} apps.")
    
    count = 0
    for app in apps:
        if app["id"] in processed_ids:
            print(f"Skipping App #{app['id']} ({app['name']}) - already processed.")
            continue
            
        # Optional check: we can retry failures if we want, or skip them
        if app["id"] in failed_ids:
            print(f"Skipping App #{app['id']} ({app['name']}) - already failed in a previous run.")
            continue
            
        try:
            # Process the app
            result = process_app(app)
            results.append(result)
            
            # Save progress incrementally
            save_json_file(RESULTS_FILE, results)
            print(f"Successfully saved results for {app['name']}.")
            
            # Sleep brief moment between apps to reduce rate-limiting
            time.sleep(2)
            
        except Exception as e:
            print(f"Error processing {app['name']}: {e}")
            traceback.print_exc()
            
            # Log failure
            failures.append({
                "id": app["id"],
                "name": app["name"],
                "category": app["category"],
                "error": str(e)
            })
            save_json_file(FAILURES_FILE, failures)
            
        count += 1
        
    print("\nResearch complete!")
    print(f"Total processed successfully: {len(results)}")
    print(f"Total failures: {len(failures)}")

if __name__ == "__main__":
    # If run directly, run a test batch of 3 apps first to make sure everything works
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "full":
        main()
    else:
        print("Starting test batch of 3 apps. Run with 'python research_agent.py full' for the full run.")
        main(batch_size=3)
