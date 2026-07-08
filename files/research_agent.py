"""
First-pass research run across all 100 apps.
Writes results incrementally (one line per app) so a crash partway through
doesn't lose earlier work — v1 only wrote at the very end.
"""
import os
import json
import time
from common import search_and_fetch_docs, extract_metadata, build_result_record

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_FILE = os.path.join(BASE_DIR, "data", "apps.json")
RESULTS_FILE = os.path.join(BASE_DIR, "data", "results_v1.json")
PROGRESS_FILE = os.path.join(BASE_DIR, "data", "results_v1.jsonl")  # incremental log

MODEL = os.environ.get("RESEARCH_MODEL", "gpt-4o-mini")  # cheap for the first pass


def run():
    apps = json.load(open(APPS_FILE, encoding="utf-8"))
    results = []

    # Resume support: skip apps already logged in the .jsonl if this is a re-run
    done_ids = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    results.append(row)
                    done_ids.add(row["id"])

    with open(PROGRESS_FILE, "a", encoding="utf-8") as progress_f:
        for app in apps:
            if app["id"] in done_ids:
                continue
            print(f"\n[{app['id']}/100] Researching {app['name']}...")
            try:
                raw_docs, evidence_url, fetch_failures, fetch_ok = search_and_fetch_docs(
                    app["name"], app.get("website", "")
                )
                extracted = extract_metadata(app, raw_docs, model=MODEL)
                record = build_result_record(app, extracted, evidence_url, fetch_ok, fetch_failures)
            except Exception as e:
                # Even a total pipeline failure becomes an honest row, not a
                # dropped app and not a silently-optimistic guess.
                record = {
                    "id": app["id"],
                    "app": app["name"],
                    "category": app["category"],
                    "one_liner": "",
                    "auth_methods": [],
                    "self_serve": "unknown",
                    "gating_notes": "",
                    "api_surface": {"type": "unknown", "breadth": "unknown", "existing_mcp": False},
                    "buildability_verdict": "unknown",
                    "blocker": "other",
                    "evidence_url": app.get("website", ""),
                    "confidence": "low",
                    "agent_notes": f"[Pipeline error, not researched: {e}]",
                    "needs_human_review": True,
                }
                print(f"  PIPELINE ERROR for {app['name']}: {e}")

            results.append(record)
            progress_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            progress_f.flush()
            time.sleep(1)  # small pacing gap; backoff inside execute_with_backoff handles 429s

    results_sorted = sorted(results, key=lambda r: r["id"])
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results_sorted, f, indent=2, ensure_ascii=False)

    flagged = [r for r in results_sorted if r.get("needs_human_review")]
    print(f"\nDone. {len(results_sorted)} apps processed, {len(flagged)} flagged for human review.")


if __name__ == "__main__":
    run()
