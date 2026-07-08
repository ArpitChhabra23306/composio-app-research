"""
research_agent.py — First-pass research run across all 100 apps.

Imports shared logic from common.py so fixes propagate to rerun_v2.py too.

Changes vs original:
- Uses common.py (no copy-pasted functions)
- Writes to a .jsonl progress file incrementally — a crash at app 80 no
  longer loses all earlier work (original wrote results_v1.json at each save
  which was ok, but this is more crash-safe)
- Resume support: re-running the script skips already-processed apps
- Pipeline errors become honest "unknown" rows with needs_human_review=True,
  not dropped apps or silent optimistic guesses
"""
import os
import sys
import json
import time

# common.py lives in the same agent/ directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import search_and_fetch_docs, extract_metadata, build_result_record

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_FILE = os.path.join(BASE_DIR, "data", "apps.json")
RESULTS_FILE = os.path.join(BASE_DIR, "data", "results_v1.json")
PROGRESS_FILE = os.path.join(BASE_DIR, "data", "results_v1.jsonl")  # incremental crash-safe log

# gpt-4o-mini for first pass (cheap), gpt-4o for the v2 rerun
MODEL = os.environ.get("RESEARCH_MODEL", "gpt-4o")


def run(batch_size=None):
    apps = json.load(open(APPS_FILE, encoding="utf-8"))
    if batch_size:
        apps = apps[:batch_size]
        print(f"Running test batch of {batch_size} apps.")

    results = []
    done_ids = set()

    # Resume: load any already-processed apps from the incremental log
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        row = json.loads(line)
                        results.append(row)
                        done_ids.add(row["id"])
                    except json.JSONDecodeError:
                        pass
        if done_ids:
            print(f"Resuming - {len(done_ids)} apps already processed, skipping them.")

    with open(PROGRESS_FILE, "a", encoding="utf-8") as progress_f:
        for app in apps:
            if app["id"] in done_ids:
                print(f"Skipping #{app['id']} {app['name']} — already processed.")
                continue

            print(f"\n{'='*50}")
            print(f"Processing App #{app['id']}: {app['name']} ({app['category']})")
            print(f"{'='*50}")

            try:
                raw_docs, evidence_url, fetch_failures, fetch_ok = search_and_fetch_docs(
                    app["name"], app.get("website", "")
                )
                extracted = extract_metadata(app, raw_docs, model=MODEL)
                record = build_result_record(app, extracted, evidence_url, fetch_ok, fetch_failures)
            except Exception as e:
                # Total pipeline failure: still produce an honest row
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
                    "agent_notes": f"[Pipeline error — app not researched: {e}]",
                    "needs_human_review": True,
                }
                print(f"  PIPELINE ERROR for {app['name']}: {e}")

            results.append(record)
            progress_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            progress_f.flush()

            if record.get("needs_human_review"):
                print(f"  WARNING: Flagged for human review: {record['agent_notes'][:120]}")

            time.sleep(2)

    # Write final sorted JSON
    results_sorted = sorted(results, key=lambda r: r["id"])
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results_sorted, f, indent=2, ensure_ascii=False)

    flagged = [r for r in results_sorted if r.get("needs_human_review")]
    print(f"\nDone. {len(results_sorted)} apps processed, {len(flagged)} flagged for human review.")
    if flagged:
        print("Flagged apps:")
        for r in flagged:
            print(f"  #{r['id']} {r['app']}: {r['agent_notes'][:80]}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=None, help="Only process first N apps (for testing)")
    args = parser.parse_args()
    run(batch_size=args.batch)
