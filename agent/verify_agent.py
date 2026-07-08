import os
import json
import time
from dotenv import load_dotenv
from openai import OpenAI
from composio import Composio

load_dotenv()

# Setup paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_V1_FILE = os.path.join(BASE_DIR, "data", "results_v1.json")
RESULTS_V2_FILE = os.path.join(BASE_DIR, "data", "results_v2.json")
VERIFICATION_SAMPLE_FILE = os.path.join(BASE_DIR, "data", "verification_sample.json")

# 20 stratified sample apps for manual/agent verification
SAMPLE_APP_IDS = [1, 4, 7, 11, 17, 21, 24, 31, 37, 41, 50, 53, 60, 61, 65, 71, 80, 81, 90, 92]

openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
composio_client = Composio(api_key=os.environ.get("COMPOSIO_API_KEY"))

VERIFY_SYSTEM_PROMPT = """You are a QA Verification Agent. Your job is to verify the accuracy of a previously extracted API research report by comparing it against fresh search results.

You are given:
1. The app name and its website hint.
2. The agent's initial findings.
3. Fresh search snippets related to this app's API access, pricing, and authentication.

Analyze them and output a JSON object indicating if the agent's findings are correct, partially correct, or wrong. Be very strict.

Focus on:
- **auth_methods**: Did the agent miss a major auth method (like OAuth2 if only API Key is listed, or vice versa)?
- **self_serve**: Did the agent claim it is self-serve when the fresh docs show it needs contact sales, enterprise plans, or manual approval? Or vice versa?
- **api_surface**: Is the API type correct?
- **blocker**: Is the blocker accurate?

Output JSON schema:
{
  "auth_methods_correct": true/false,
  "self_serve_correct": true/false,
  "api_surface_correct": true/false,
  "blocker_correct": true/false,
  "evidence_url_valid": true/false,
  "mismatch_details": "Explain any mismatches found (e.g. 'Agent missed OAuth2; app supports both OAuth2 and API Key. Gating was reported as self-serve but fresh docs show it requires Enterprise plan for API access.')",
  "recommended_corrections": {
    "auth_methods": ["OAuth2", "API Key"], // only include fields that need correction
    "self_serve": "gated",
    "blocker": "needs paid plan"
  }
}
"""

VERIFY_USER_TEMPLATE = """App: {app_name}
Website: {website}

---
AGENT INITIAL FINDINGS (v1):
One-liner: {one_liner}
Auth methods: {auth_methods}
Self-serve/Gated: {self_serve}
Gating notes: {gating_notes}
API type: {api_type}
API breadth: {api_breadth}
Blocker: {blocker}
Evidence URL: {evidence_url}
---

FRESH SEARCH RESULTS:
{search_results}

Compare and verify each field. Output ONLY the valid JSON object.
"""

def load_json_file(file_path, default=None):
    if default is None:
        default = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default

def save_json_file(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def verify_app(app_data):
    """Executes a search to double check app gating and auth details, and calls the LLM to verify."""
    app_name = app_data["app"]
    website = app_data["evidence_url"]
    
    # Run a verify search focused on auth and pricing/gating
    query = f"{app_name} API developer key price oauth access limit"
    print(f"Running verification search for {app_name}: '{query}'")
    
    try:
        res = composio_client.client.tools.execute(
            tool_slug="COMPOSIO_SEARCH_DUCK_DUCK_GO",
            arguments={"query": query}
        )
        search_snippets = []
        if res.successful:
            for r in res.data.get("results", [])[:5]:
                search_snippets.append(f"Title: {r['title']}\nSnippet: {r['snippet']}\nLink: {r['link']}")
        snippets_text = "\n".join(search_snippets)
    except Exception as e:
        print(f"Verification search failed for {app_name}: {e}")
        snippets_text = "No search results available due to tool error."

    user_prompt = VERIFY_USER_TEMPLATE.format(
        app_name=app_name,
        website=website,
        one_liner=app_data["one_liner"],
        auth_methods=app_data["auth_methods"],
        self_serve=app_data["self_serve"],
        gating_notes=app_data["gating_notes"],
        api_type=app_data["api_surface"]["type"],
        api_breadth=app_data["api_surface"]["breadth"],
        blocker=app_data["blocker"],
        evidence_url=app_data["evidence_url"],
        search_results=snippets_text
    )

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.0
    )
    
    report = json.loads(response.choices[0].message.content)
    return report

def main():
    results_v1 = load_json_file(RESULTS_V1_FILE)
    if not results_v1:
        print("No results_v1.json found. Make sure the research agent has finished running.")
        return
        
    print(f"Loaded {len(results_v1)} apps from results_v1.json.")
    
    # Filter results for the 20 sample apps
    sample_apps_v1 = [r for r in results_v1 if r["id"] in SAMPLE_APP_IDS]
    print(f"Found {len(sample_apps_v1)} of the sample apps in the v1 output.")
    
    verification_reports = load_json_file(VERIFICATION_SAMPLE_FILE, default={})
    
    correct_count = 0
    total_checked = 0
    
    for app_data in sample_apps_v1:
        app_id_str = str(app_data["id"])
        
        # Skip if already verified in this session to avoid extra API calls
        if app_id_str in verification_reports:
            print(f"Skipping App #{app_data['id']}: {app_data['app']} - already verified.")
            total_checked += 1
            report = verification_reports[app_id_str]["report"]
            if all([report["auth_methods_correct"], report["self_serve_correct"], report["blocker_correct"]]):
                correct_count += 1
            continue
            
        print(f"\nVerifying App #{app_data['id']}: {app_data['app']}")
        try:
            report = verify_app(app_data)
            
            # Save verification details
            verification_reports[app_id_str] = {
                "app": app_data["app"],
                "v1_data": app_data,
                "report": report
            }
            save_json_file(VERIFICATION_SAMPLE_FILE, verification_reports)
            
            # Print verification summary
            all_correct = all([report["auth_methods_correct"], report["self_serve_correct"], report["blocker_correct"]])
            if all_correct:
                print(f"-> App verified as CORRECT.")
                correct_count += 1
            else:
                print(f"-> Mismatch detected! Details: {report['mismatch_details']}")
                
            total_checked += 1
            time.sleep(2)
        except Exception as e:
            print(f"Failed to verify {app_data['app']}: {e}")
            
    if total_checked > 0:
        accuracy = (correct_count / total_checked) * 100
        print(f"\nVerification Batch complete!")
        print(f"Total checked: {total_checked}")
        print(f"Fully correct: {correct_count}")
        print(f"Verification accuracy: {accuracy:.2f}%")
        
        # Save verification overview stats
        stats = {
            "total_checked": total_checked,
            "fully_correct": correct_count,
            "accuracy_percent": accuracy
        }
        save_json_file(os.path.join(BASE_DIR, "data", "verification_stats.json"), stats)
    else:
        print("No apps were verified.")

if __name__ == "__main__":
    main()
