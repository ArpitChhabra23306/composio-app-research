"""
research_agent_v2.py — Full V3 pipeline run across all 100 apps.

This is the clean, post-Claude-review version that:
  - Writes to results_v2.json (separate from v1/v2 so we can compare all three)
  - Imports all logic from common.py (no copy-paste)
  - Crash-safe incremental writes to results_v2.jsonl
  - Honest failure defaults — no silent optimistic guesses
  - Uses gpt-4o with temperature=0 throughout
  - Full resume support — safe to interrupt and restart
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import search_and_fetch_docs, extract_metadata, build_result_record

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_FILE    = os.path.join(BASE_DIR, "data", "apps.json")
RESULTS_FILE = os.path.join(BASE_DIR, "data", "results_v2.json")
PROGRESS_FILE= os.path.join(BASE_DIR, "data", "results_v2.jsonl")

MODEL = "gpt-4o"


def run(batch_size=None, start_from=None):
    apps = json.load(open(APPS_FILE, encoding="utf-8"))
    if batch_size:
        apps = apps[:batch_size]
    if start_from:
        apps = [a for a in apps if a["id"] >= start_from]

    results = []
    done_ids = set()

    # Resume from crash-safe log
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    results.append(row)
                    done_ids.add(row["id"])
                except json.JSONDecodeError:
                    pass
        if done_ids:
            print(f"[RESUME] {len(done_ids)} apps already done, skipping them.")

    total = len(apps)
    remaining = [a for a in apps if a["id"] not in done_ids]
    print(f"\nV2 Full Run | {len(remaining)} apps to process (of {total} total) | model={MODEL}\n")

    with open(PROGRESS_FILE, "a", encoding="utf-8") as pf:
        for i, app in enumerate(remaining):
            pct = int((i / max(len(remaining), 1)) * 100)
            print(f"\n[{i+1}/{len(remaining)} | {pct}%] App #{app['id']}: {app['name']} ({app['category']})")
            print("-" * 55)

            try:
                raw_docs, evidence_url, fetch_failures, fetch_ok = search_and_fetch_docs(
                    app["name"], app.get("website", "")
                )
                extracted = extract_metadata(app, raw_docs, model=MODEL)
                record = build_result_record(app, extracted, evidence_url, fetch_ok, fetch_failures)
            except Exception as e:
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
                    "agent_notes": f"[Pipeline error: {e}]",
                    "needs_human_review": True,
                }
                print(f"  PIPELINE ERROR: {e}")

            record["v2_run"] = True
            results.append(record)
            pf.write(json.dumps(record, ensure_ascii=False) + "\n")
            pf.flush()

            auth    = record.get("auth_methods", [])
            ss      = record.get("self_serve", "?")
            blk     = record.get("blocker", "?")
            conf    = record.get("confidence", "?")
            flag    = " [REVIEW]" if record.get("needs_human_review") else ""
            print(f"  auth={auth} | ss={ss} | blocker={blk} | conf={conf}{flag}")

            time.sleep(2)

    # Write final sorted JSON
    results_sorted = sorted(results, key=lambda r: r["id"])
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results_sorted, f, indent=2, ensure_ascii=False)

    flagged = [r for r in results_sorted if r.get("needs_human_review")]
    unknown  = [r for r in results_sorted if r.get("buildability_verdict") == "unknown"]
    print(f"\n{'='*55}")
    print(f"V2 COMPLETE: {len(results_sorted)}/100 apps processed")
    print(f"  Flagged for review: {len(flagged)}")
    print(f"  Unknown (pipeline errors): {len(unknown)}")
    print(f"  Results written to: {RESULTS_FILE}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, default=None)
    p.add_argument("--from-id", type=int, default=None)
    args = p.parse_args()
    run(batch_size=args.batch, start_from=args.from_id)
