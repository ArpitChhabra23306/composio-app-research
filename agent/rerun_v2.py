"""
rerun_v2.py — V2 rerun with improved prompt and gpt-4o.

=== THE BUG THIS FIXES (original rerun_failed.py) ===
The original only re-ran these 14 specific IDs:
  FAILED_IDS = {1, 4, 7, 11, 31, 37, 41, 50, 53, 60, 65, 81, 90, 92}

These 14 were caught in the 20-app manual verification sample. But the V2
prompt fixes SYSTEMATIC biases that affect the entire 100-app dataset:
  - Under-detecting multi-auth (OAuth2 + API Key both present)
  - Over-optimistic self-serve classification

Rerunning only the 14 known-bad apps means the "v1 → v2 accuracy improved"
claim only holds for rows you already knew were wrong. The ~80 unsampled
rows almost certainly have the same systematic errors and were never touched.

This script supports three scopes:
  --scope known_bad   Only the 14 IDs caught in manual verification
                      (fast, but the weakest methodological claim)
  --scope low_conf    Everything v1 flagged confidence != "high" or
                      needs_human_review=True (good middle ground)
  --scope all         Full 100 (strongest claim, ~35 min at 2s/app with gpt-4o)

Usage:
  python rerun_v2.py --scope all
  python rerun_v2.py --scope low_conf
  python rerun_v2.py --scope known_bad --ids 1,4,7,11,31,37,41,50,53,60,65,81,90,92

=== SDK CALL SHAPE NOTE ===
Uses common.py which has been verified against the live account.
The CORRECT call is composio_client.client.tools.execute(tool_slug=..., arguments=...).
Do NOT switch to composio_client.tools.execute(slug=...) — that path requires
a toolkit version parameter and throws ToolVersionRequiredError without one.
"""
import os
import sys
import json
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import search_and_fetch_docs, extract_metadata, build_result_record

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_FILE = os.path.join(BASE_DIR, "data", "apps.json")
RESULTS_V1_FILE = os.path.join(BASE_DIR, "data", "results_v1.json")
RESULTS_V2_FILE = os.path.join(BASE_DIR, "data", "results_v2.json")

MODEL = os.environ.get("RERUN_MODEL", "gpt-4o")  # Always gpt-4o for v2

# The 14 app IDs caught in the original 20-app manual verification pass
KNOWN_BAD_IDS = [1, 4, 7, 11, 31, 37, 41, 50, 53, 60, 65, 81, 90, 92]


def select_scope(scope, apps_by_id, v1_by_id, explicit_ids):
    """Returns the list of app IDs to re-run based on scope argument."""
    if scope == "known_bad":
        ids = explicit_ids if explicit_ids else KNOWN_BAD_IDS
        print(f"Scope: known_bad — re-running {len(ids)} manually-identified failures")
        print("  NOTE: This only proves improvement on the rows you already knew were wrong.")
        print("  Use --scope all or --scope low_conf for a more defensible accuracy claim.")
        return ids

    if scope == "all":
        ids = sorted(apps_by_id.keys())
        print(f"Scope: all — re-running all {len(ids)} apps with v2 prompt")
        print("  This is the most defensible approach: proves the prompt improvement is general.")
        return ids

    if scope == "low_conf":
        ids = [
            app_id for app_id, r in v1_by_id.items()
            if r.get("confidence") != "high" or r.get("needs_human_review")
        ]
        ids = sorted(ids)
        print(f"Scope: low_conf — re-running {len(ids)} apps v1 flagged as non-high-confidence")
        print("  Good middle ground: covers the most uncertain rows without full 100-app cost.")
        return ids

    raise ValueError(f"Unknown scope: {scope!r}. Choose: known_bad, low_conf, all")


def main():
    parser = argparse.ArgumentParser(description="Re-run research with v2 prompt and gpt-4o")
    parser.add_argument(
        "--scope",
        choices=["known_bad", "low_conf", "all"],
        default="low_conf",
        help="Which apps to re-run (default: low_conf)"
    )
    parser.add_argument(
        "--ids",
        default="",
        help="Comma-separated app IDs (only used with --scope known_bad)"
    )
    args = parser.parse_args()

    apps = json.load(open(APPS_FILE, encoding="utf-8"))
    results_v1 = json.load(open(RESULTS_V1_FILE, encoding="utf-8"))

    apps_by_id = {a["id"]: a for a in apps}
    v1_by_id = {r["id"]: r for r in results_v1}

    explicit_ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()] if args.ids else []
    target_ids = select_scope(args.scope, apps_by_id, v1_by_id, explicit_ids)

    # Seed from v1 — only overwrite target_ids, keep everything else
    updated_results = dict(v1_by_id)

    print(f"\nStarting re-run of {len(target_ids)} apps with model={MODEL}...\n")

    for app_id in sorted(target_ids):
        app = apps_by_id.get(app_id)
        if not app:
            print(f"  WARNING: App ID {app_id} not found in apps.json, skipping.")
            continue

        print(f"\n{'='*50}")
        print(f"Re-running App #{app_id}: {app['name']} ({app['category']})")
        print(f"{'='*50}")

        try:
            raw_docs, evidence_url, fetch_failures, fetch_ok = search_and_fetch_docs(
                app["name"], app.get("website", "")
            )
            extracted = extract_metadata(app, raw_docs, model=MODEL)
            record = build_result_record(app, extracted, evidence_url, fetch_ok, fetch_failures)
            record["v2_rerun"] = True
            record["v2_scope"] = args.scope
            updated_results[app_id] = record

            auth = record["auth_methods"]
            ss = record["self_serve"]
            blk = record["blocker"]
            conf = record["confidence"]
            flag = " ⚠ REVIEW" if record.get("needs_human_review") else ""
            print(f"  → auth={auth} | self_serve={ss} | blocker={blk} | conf={conf}{flag}")

        except Exception as e:
            print(f"  ERROR re-running {app['name']}: {e}")
            # Keep v1 result but append a note — do NOT silently drop
            if app_id in updated_results:
                prev_notes = updated_results[app_id].get("agent_notes", "")
                updated_results[app_id]["agent_notes"] = \
                    (prev_notes + " " if prev_notes else "") + f"[v2 rerun failed: {e}]"
                updated_results[app_id]["needs_human_review"] = True

        time.sleep(2)

    # Write v2 results sorted by ID
    v2_results = sorted(updated_results.values(), key=lambda x: x["id"])
    with open(RESULTS_V2_FILE, "w", encoding="utf-8") as f:
        json.dump(v2_results, f, indent=2, ensure_ascii=False)

    reran = sum(1 for r in v2_results if r.get("v2_rerun"))
    flagged = sum(1 for r in v2_results if r.get("needs_human_review"))
    print(f"\n{'='*50}")
    print(f"Done. {reran}/{len(v2_results)} apps updated with v2 prompt.")
    print(f"{flagged} total apps flagged for human review across full dataset.")
    print(f"Results written to: {RESULTS_V2_FILE}")


if __name__ == "__main__":
    main()
