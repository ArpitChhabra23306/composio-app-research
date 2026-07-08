"""
compare_versions.py — Compare V1, V2, V3 results side-by-side.

Outputs:
  data/version_comparison.json  — per-app diff table
  data/accuracy_all.json        — aggregate accuracy stats across all versions
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load(name):
    p = os.path.join(BASE_DIR, "data", name)
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def index_by_id(records):
    return {r["id"]: r for r in records} if records else {}


def field_changed(v1r, v2r, field):
    a = v1r.get(field) if v1r else None
    b = v2r.get(field) if v2r else None
    return a != b


def main():
    v1 = load("results_v1.json")
    v2 = load("results_v2.json")
    v3 = load("results_v3.json")

    v1i = index_by_id(v1)
    v2i = index_by_id(v2)
    v3i = index_by_id(v3)

    all_ids = sorted(set(list(v1i.keys()) + list(v2i.keys()) + list(v3i.keys())))

    comparison = []
    for app_id in all_ids:
        r1 = v1i.get(app_id, {})
        r2 = v2i.get(app_id, {})
        r3 = v3i.get(app_id, {})

        # use whichever has the name
        name = r3.get("app") or r2.get("app") or r1.get("app", f"App_{app_id}")
        cat  = r3.get("category") or r2.get("category") or r1.get("category", "")

        row = {
            "id": app_id,
            "app": name,
            "category": cat,
            "v1_auth":  r1.get("auth_methods"),
            "v1_ss":    r1.get("self_serve"),
            "v1_blk":   r1.get("blocker"),
            "v1_conf":  r1.get("confidence"),
            "v2_auth":  r2.get("auth_methods"),
            "v2_ss":    r2.get("self_serve"),
            "v2_blk":   r2.get("blocker"),
            "v2_conf":  r2.get("confidence"),
            "v3_auth":  r3.get("auth_methods"),
            "v3_ss":    r3.get("self_serve"),
            "v3_blk":   r3.get("blocker"),
            "v3_conf":  r3.get("confidence"),
            "auth_changed_v1_v3": field_changed(r1, r3, "auth_methods"),
            "ss_changed_v1_v3":   field_changed(r1, r3, "self_serve"),
            "blk_changed_v1_v3":  field_changed(r1, r3, "blocker"),
        }
        comparison.append(row)

    # Count changes
    auth_changes = sum(1 for r in comparison if r["auth_changed_v1_v3"])
    ss_changes   = sum(1 for r in comparison if r["ss_changed_v1_v3"])
    blk_changes  = sum(1 for r in comparison if r["blk_changed_v1_v3"])

    def dist(records, field):
        if not records:
            return {}
        from collections import Counter
        return dict(Counter(r.get(field, "unknown") for r in records))

    def avg_auth_methods(records):
        if not records:
            return 0
        total = sum(len(r.get("auth_methods") or []) for r in records)
        return round(total / len(records), 2)

    summary = {
        "versions_available": {
            "v1": bool(v1), "v2": bool(v2), "v3": bool(v3)
        },
        "app_counts": {
            "v1": len(v1) if v1 else 0,
            "v2": len(v2) if v2 else 0,
            "v3": len(v3) if v3 else 0,
        },
        "v1_stats": {
            "self_serve_dist":     dist(v1, "self_serve"),
            "blocker_dist":        dist(v1, "blocker"),
            "confidence_dist":     dist(v1, "confidence"),
            "buildability_dist":   dist(v1, "buildability_verdict"),
            "avg_auth_methods_per_app": avg_auth_methods(v1),
        } if v1 else None,
        "v2_stats": {
            "self_serve_dist":     dist(v2, "self_serve"),
            "blocker_dist":        dist(v2, "blocker"),
            "confidence_dist":     dist(v2, "confidence"),
            "buildability_dist":   dist(v2, "buildability_verdict"),
            "avg_auth_methods_per_app": avg_auth_methods(v2),
        } if v2 else None,
        "v3_stats": {
            "self_serve_dist":     dist(v3, "self_serve"),
            "blocker_dist":        dist(v3, "blocker"),
            "confidence_dist":     dist(v3, "confidence"),
            "buildability_dist":   dist(v3, "buildability_verdict"),
            "avg_auth_methods_per_app": avg_auth_methods(v3),
            "needs_review_count":  sum(1 for r in v3 if r.get("needs_human_review")) if v3 else 0,
        } if v3 else None,
        "v1_to_v3_changes": {
            "auth_methods_changed": auth_changes,
            "self_serve_changed":   ss_changes,
            "blocker_changed":      blk_changes,
            "total_apps_compared":  len(comparison),
        } if v3 else None,
    }

    out_cmp  = os.path.join(BASE_DIR, "data", "version_comparison.json")
    out_summ = os.path.join(BASE_DIR, "data", "accuracy_all.json")

    with open(out_cmp, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)

    with open(out_summ, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("Version comparison written to:", out_cmp)
    print("Accuracy summary written to:  ", out_summ)

    if summary["v3_stats"]:
        s = summary["v3_stats"]
        print(f"\nV3 Self-serve dist:   {s['self_serve_dist']}")
        print(f"V3 Blocker dist:      {s['blocker_dist']}")
        print(f"V3 Confidence dist:   {s['confidence_dist']}")
        print(f"V3 Avg auth methods:  {s['avg_auth_methods_per_app']}")
        print(f"V3 Needs review:      {s['needs_review_count']}")

    if summary["v1_to_v3_changes"]:
        c = summary["v1_to_v3_changes"]
        print(f"\nV1->V3 changes: auth={c['auth_methods_changed']} ss={c['self_serve_changed']} blocker={c['blocker_changed']}")


if __name__ == "__main__":
    main()
