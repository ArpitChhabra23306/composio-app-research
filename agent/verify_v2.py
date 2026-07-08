"""
verify_v2.py — Verification script for the V2 run.

Picks a stratified random sample of 20 apps from results_v2.json,
re-checks them independently using fresh web searches + doc fetches,
and reports field-level accuracy against the agent's answers.

Stratification ensures we check:
  - 5 apps the agent marked HIGH confidence
  - 5 apps the agent marked MED confidence
  - 5 apps the agent marked LOW confidence / flagged for review
  - 5 apps from the old V1 known-bad list (to confirm improvement)
"""
import os
import sys
import json
import random
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import execute_with_backoff, SEARCH_TOOL_SLUG, FETCH_TOOL_SLUG

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V3_FILE = os.path.join(BASE_DIR, "data", "results_v2.json")
V1_FILE = os.path.join(BASE_DIR, "data", "results_v1.json")
OUTPUT  = os.path.join(BASE_DIR, "data", "verification_v2.json")

# The 14 known-bad IDs from V1 that we re-ran in V2/V3
V1_KNOWN_BAD = {1, 4, 7, 11, 31, 37, 41, 50, 53, 60, 65, 81, 90, 92}


VERIFIER_PROMPT = """You are a careful fact-checker. Given fresh documentation content fetched from the web,
verify these specific claims about {app_name}:

AGENT CLAIMS:
  auth_methods: {auth_methods}
  self_serve:   {self_serve}
  blocker:      {blocker}
  buildability: {buildability}

FRESH DOCS CONTENT:
{docs_content}

Based ONLY on the fresh docs content above, answer:
1. Are the auth_methods correct? List what you found in the docs.
2. Is self_serve correctly classified? What does the docs say about free/paid access?
3. Is the blocker/buildability correct?

Output ONLY valid JSON:
{{
  "auth_methods_correct": true/false,
  "auth_methods_found": ["list", "of", "what", "docs", "actually", "say"],
  "self_serve_correct": true/false,
  "self_serve_found": "self-serve|gated|mixed based on docs",
  "buildability_correct": true/false,
  "verdict": "correct|partially_correct|wrong",
  "notes": "brief explanation of what matched and what didn't"
}}"""


def verify_app(record, v1_record=None):
    """Re-fetch docs for an app and verify the agent's claims independently."""
    app_name = record["app"]
    website  = record.get("evidence_url") or record.get("website", "")

    print(f"\n  Verifying #{record['id']} {app_name}...")

    # Fresh search
    q = f"{app_name} API authentication developer documentation"
    data = execute_with_backoff(SEARCH_TOOL_SLUG, {"query": q})
    results = [] if data.get("_failed") else data.get("results", [])
    urls = [r["link"] for r in results[:3] if "link" in r]
    if website and website not in urls:
        urls.insert(0, website)

    # Fetch first good page
    fresh_text = ""
    fresh_url = ""
    for url in urls[:3]:
        fd = execute_with_backoff(FETCH_TOOL_SLUG, {"url": url})
        if fd.get("_failed"):
            continue
        page = fd.get("results", [])
        if page and len(page[0].get("text", "")) > 300:
            fresh_text = page[0]["text"][:8000]
            fresh_url  = url
            break

    if not fresh_text:
        return {
            "id": record["id"],
            "app": app_name,
            "category": record["category"],
            "agent_conf": record.get("confidence", "?"),
            "v3_auth": record.get("auth_methods", []),
            "v3_ss": record.get("self_serve", "?"),
            "v3_blocker": record.get("blocker", "?"),
            "v1_auth": v1_record.get("auth_methods", []) if v1_record else None,
            "v1_ss": v1_record.get("self_serve", "?") if v1_record else None,
            "verify_result": "skipped_no_content",
            "fresh_url": "",
            "notes": "Could not fetch fresh docs for verification"
        }

    # LLM cross-check
    prompt = VERIFIER_PROMPT.format(
        app_name=app_name,
        auth_methods=record.get("auth_methods", []),
        self_serve=record.get("self_serve", "?"),
        blocker=record.get("blocker", "?"),
        buildability=record.get("buildability_verdict", "?"),
        docs_content=fresh_text
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.0
    )
    check = json.loads(resp.choices[0].message.content)

    return {
        "id": record["id"],
        "app": app_name,
        "category": record["category"],
        "agent_conf": record.get("confidence", "?"),
        # V3 claims
        "v3_auth": record.get("auth_methods", []),
        "v3_ss": record.get("self_serve", "?"),
        "v3_blocker": record.get("blocker", "?"),
        "v3_buildability": record.get("buildability_verdict", "?"),
        # V1 for comparison
        "v1_auth": v1_record.get("auth_methods", []) if v1_record else None,
        "v1_ss":   v1_record.get("self_serve", "?") if v1_record else None,
        # Verification results
        "auth_correct": check.get("auth_methods_correct"),
        "auth_found": check.get("auth_methods_found", []),
        "ss_correct": check.get("self_serve_correct"),
        "ss_found": check.get("self_serve_found"),
        "build_correct": check.get("buildability_correct"),
        "verdict": check.get("verdict", "unknown"),
        "fresh_url": fresh_url,
        "notes": check.get("notes", "")
    }


def pick_sample(v3_records, v1_by_id, n=20):
    """Stratified sample: high conf / med conf / low conf / known-bad fixed IDs."""
    high = [r for r in v3_records if r.get("confidence") == "high"]
    med  = [r for r in v3_records if r.get("confidence") == "med"]
    low  = [r for r in v3_records if r.get("confidence") in ("low", None) or r.get("needs_human_review")]
    bad  = [r for r in v3_records if r["id"] in V1_KNOWN_BAD]

    seed = 42
    random.seed(seed)
    chosen = set()

    # 5 from known-bad (to verify improvement over V1)
    for r in random.sample(bad, min(5, len(bad))):
        chosen.add(r["id"])

    # 5 high conf
    for r in random.sample([x for x in high if x["id"] not in chosen], min(5, len(high))):
        chosen.add(r["id"])

    # 5 med conf
    candidates_med = [x for x in med if x["id"] not in chosen]
    for r in random.sample(candidates_med, min(5, len(candidates_med))):
        chosen.add(r["id"])

    # Fill up to 20 with remaining low/review
    candidates_low = [x for x in low if x["id"] not in chosen]
    remaining = n - len(chosen)
    if remaining > 0 and candidates_low:
        for r in random.sample(candidates_low, min(remaining, len(candidates_low))):
            chosen.add(r["id"])

    return [r for r in v3_records if r["id"] in chosen]


def compute_stats(verifications):
    total = len([v for v in verifications if v.get("verdict") not in (None, "skipped_no_content")])
    if total == 0:
        return {}
    correct  = sum(1 for v in verifications if v.get("verdict") == "correct")
    partial  = sum(1 for v in verifications if v.get("verdict") == "partially_correct")
    wrong    = sum(1 for v in verifications if v.get("verdict") == "wrong")
    auth_ok  = sum(1 for v in verifications if v.get("auth_correct") is True)
    ss_ok    = sum(1 for v in verifications if v.get("ss_correct") is True)
    build_ok = sum(1 for v in verifications if v.get("build_correct") is True)
    return {
        "total_verified": total,
        "overall_accuracy_pct": round(correct / total * 100, 1),
        "correct": correct,
        "partially_correct": partial,
        "wrong": wrong,
        "auth_accuracy_pct": round(auth_ok / total * 100, 1),
        "self_serve_accuracy_pct": round(ss_ok / total * 100, 1),
        "buildability_accuracy_pct": round(build_ok / total * 100, 1),
    }


def main():
    if not os.path.exists(V3_FILE):
        print(f"ERROR: {V3_FILE} not found — run research_agent_v2.py first")
        return

    v3 = json.load(open(V3_FILE, encoding="utf-8"))
    v1 = json.load(open(V1_FILE, encoding="utf-8"))
    v1_by_id = {r["id"]: r for r in v1}

    sample = pick_sample(v3, v1_by_id, n=20)
    print(f"Selected {len(sample)} apps for verification (stratified sample)")
    for r in sorted(sample, key=lambda x: x["id"]):
        conf = r.get("confidence", "?")
        flag = " [KNOWN_BAD_V1]" if r["id"] in V1_KNOWN_BAD else ""
        print(f"  #{r['id']} {r['app']} (conf={conf}){flag}")

    verifications = []
    for r in sorted(sample, key=lambda x: x["id"]):
        v1r = v1_by_id.get(r["id"])
        result = verify_app(r, v1r)
        verifications.append(result)
        time.sleep(2)

    stats = compute_stats(verifications)
    output = {
        "run_info": {
            "total_apps_in_v3": len(v3),
            "sample_size": len(sample),
            "model": "gpt-4o",
            "stratification": "5 known_bad + 5 high_conf + 5 med_conf + 5 low_conf/review"
        },
        "accuracy_stats": stats,
        "verifications": sorted(verifications, key=lambda x: x["id"])
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*55}")
    print("VERIFICATION COMPLETE")
    print(f"  Overall accuracy: {stats.get('overall_accuracy_pct', 'N/A')}%")
    print(f"  Auth accuracy:    {stats.get('auth_accuracy_pct', 'N/A')}%")
    print(f"  Self-serve acc:   {stats.get('self_serve_accuracy_pct', 'N/A')}%")
    print(f"  Buildability acc: {stats.get('buildability_accuracy_pct', 'N/A')}%")
    print(f"  Results: {OUTPUT}")


if __name__ == "__main__":
    main()
