"""
V2 rerun.

Fixed vs the original rerun_failed.py: that script only re-ran the 14 app
IDs caught in the manual verification sample. But the whole point of the
V2 prompt is to fix SYSTEMATIC biases (under-detecting multi-auth methods,
over-optimistic self-serve calls) that logically affect apps beyond the
~15-20 that were manually sampled. Re-running only the known-bad rows means
the "v1 -> v2 accuracy improved" claim is only proven on rows you already
knew were wrong -- it says nothing about the other ~80 unsampled rows.

This script supports three scopes via --scope:
  known_bad   - only the specific IDs caught in manual verification
                (fast, but doesn't prove the fix generalizes)
  low_conf    - every app v1 flagged as confidence != "high", or that
                needs_human_review -- a reasonable middle ground
  all         - the full 100 (most defensible, most expensive/slowest;
                do this if time budget allows)

Usage:
  python rerun_v2.py --scope all
  python rerun_v2.py --scope low_conf
  python rerun_v2.py --scope known_bad --ids 1,4,7,11,31,37,41,50,53,60,65,81,90,92
"""
import os
import json
import time
import argparse
from common import search_and_fetch_docs, extract_metadata, build_result_record

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_FILE = os.path.join(BASE_DIR, "data", "apps.json")
RESULTS_V1_FILE = os.path.join(BASE_DIR, "data", "results_v1.json")
RESULTS_V2_FILE = os.path.join(BASE_DIR, "data", "results_v2.json")

MODEL = os.environ.get("RERUN_MODEL", "gpt-4o")  # upgraded model for the fixed prompt


def select_scope(scope, apps_by_id, v1_by_id, explicit_ids):
    if scope == "known_bad":
        return explicit_ids
    if scope == "all":
        return list(apps_by_id.keys())
    if scope == "low_conf":
        return [
            app_id for app_id, r in v1_by_id.items()
            if r.get("confidence") != "high" or r.get("needs_human_review")
        ]
    raise ValueError(f"Unknown scope: {scope}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["known_bad", "low_conf", "all"], default="low_conf")
    parser.add_argument("--ids", default="", help="comma-separated app IDs, used only with --scope known_bad")
    args = parser.parse_args()

    apps = json.load(open(APPS_FILE, encoding="utf-8"))
    results_v1 = json.load(open(RESULTS_V1_FILE, encoding="utf-8"))

    apps_by_id = {a["id"]: a for a in apps}
    v1_by_id = {r["id"]: r for r in results_v1}

    explicit_ids = [int(x) for x in args.ids.split(",") if x.strip()] if args.ids else []
    target_ids = select_scope(args.scope, apps_by_id, v1_by_id, explicit_ids)

    print(f"Rerunning {len(target_ids)} apps under scope='{args.scope}'...")
    updated_results = dict(v1_by_id)  # seed from v1, overwrite only what's rerun

    for app_id in sorted(target_ids):
        app = apps_by_id.get(app_id)
        if not app:
            continue
        print(f"\nRe-running App #{app_id}: {app['name']}")
        try:
            raw_docs, evidence_url, fetch_failures, fetch_ok = search_and_fetch_docs(
                app["name"], app.get("website", "")
            )
            extracted = extract_metadata(app, raw_docs, model=MODEL)
            record = build_result_record(app, extracted, evidence_url, fetch_ok, fetch_failures)
            record["v2_rerun"] = True
            updated_results[app_id] = record
        except Exception as e:
            print(f"Error re-running {app['name']}: {e}")
            # Keep the v1 result but flag it rather than silently dropping it
            if app_id in updated_results:
                updated_results[app_id]["agent_notes"] += f" [v2 rerun failed: {e}]"
                updated_results[app_id]["needs_human_review"] = True
        time.sleep(1)

    v2_results = sorted(updated_results.values(), key=lambda x: x["id"])
    with open(RESULTS_V2_FILE, "w", encoding="utf-8") as f:
        json.dump(v2_results, f, indent=2, ensure_ascii=False)

    reran = sum(1 for r in v2_results if r.get("v2_rerun"))
    print(f"\nDone. {reran}/{len(v2_results)} apps updated under scope='{args.scope}'.")


if __name__ == "__main__":
    main()
