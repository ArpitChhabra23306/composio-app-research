import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_FILE = os.path.join(BASE_DIR, "data", "results_v2.json")
# Fallback to results_v1.json if results_v2.json is not created yet
if not os.path.exists(RESULTS_FILE):
    RESULTS_FILE = os.path.join(BASE_DIR, "data", "results_v1.json")

PATTERNS_FILE = os.path.join(BASE_DIR, "data", "patterns.json")

def load_json_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def main():
    results = load_json_file(RESULTS_FILE)
    if not results:
        print(f"No results file found at {RESULTS_FILE}")
        return
        
    print(f"Analyzing patterns for {len(results)} apps...")
    
    # 1. Auth method distribution
    auth_counts = {}
    total_auth_occurrences = 0
    for r in results:
        for auth in r["auth_methods"]:
            auth_counts[auth] = auth_counts.get(auth, 0) + 1
            total_auth_occurrences += 1
            
    auth_distribution = {
        auth: {
            "count": count,
            "percentage": round((count / len(results)) * 100, 2)
        } for auth, count in auth_counts.items()
    }
    
    # 2. Self-serve vs Gated vs Mixed split
    self_serve_counts = {}
    for r in results:
        val = r["self_serve"]
        self_serve_counts[val] = self_serve_counts.get(val, 0) + 1
        
    self_serve_distribution = {
        val: {
            "count": count,
            "percentage": round((count / len(results)) * 100, 2)
        } for val, count in self_serve_counts.items()
    }
    
    # 3. Blocker distribution
    blocker_counts = {}
    for r in results:
        val = r["blocker"]
        blocker_counts[val] = blocker_counts.get(val, 0) + 1
        
    blocker_distribution = {
        val: {
            "count": count,
            "percentage": round((count / len(results)) * 100, 2)
        } for val, count in blocker_counts.items()
    }
    
    # 4. Buildability distribution
    buildability_counts = {}
    for r in results:
        val = r["buildability_verdict"]
        buildability_counts[val] = buildability_counts.get(val, 0) + 1
        
    buildability_distribution = {
        val: {
            "count": count,
            "percentage": round((count / len(results)) * 100, 2)
        } for val, count in buildability_counts.items()
    }
    
    # 5. Category analysis
    category_data = {}
    for r in results:
        cat = r["category"]
        if cat not in category_data:
            category_data[cat] = {
                "total_apps": 0,
                "self_serve": 0,
                "gated": 0,
                "mixed": 0,
                "auth_methods": {},
                "mcp_count": 0,
                "buildable_count": 0
            }
            
        cdata = category_data[cat]
        cdata["total_apps"] += 1
        cdata[r["self_serve"]] += 1
        if r["api_surface"]["existing_mcp"]:
            cdata["mcp_count"] += 1
        if r["buildability_verdict"] == "buildable today":
            cdata["buildable_count"] += 1
            
        for auth in r["auth_methods"]:
            cdata["auth_methods"][auth] = cdata["auth_methods"].get(auth, 0) + 1
            
    # Normalize category data for easy presentation
    for cat, data in category_data.items():
        data["self_serve_percent"] = round((data["self_serve"] / data["total_apps"]) * 100, 2)
        data["gated_percent"] = round((data["gated"] / data["total_apps"]) * 100, 2)
        data["mixed_percent"] = round((data["mixed"] / data["total_apps"]) * 100, 2)
        
        # Sort auth methods
        sorted_auth = sorted(data["auth_methods"].items(), key=lambda x: x[1], reverse=True)
        data["primary_auth"] = sorted_auth[0][0] if sorted_auth else "None"
        
    # 6. Easy wins: Buildable today + Self-serve + No existing MCP
    easy_wins = []
    for r in results:
        if (r["buildability_verdict"] == "buildable today" and 
            r["self_serve"] == "self-serve" and 
            not r["api_surface"]["existing_mcp"]):
            easy_wins.append({
                "app": r["app"],
                "category": r["category"],
                "auth": r["auth_methods"],
                "website": r["evidence_url"]
            })
            
    # 7. Needs outreach: Gated + Blocker is partnership / contact-sales
    needs_outreach = []
    for r in results:
        if r["self_serve"] == "gated" and r["blocker"] in ["needs partnership", "other"]:
            needs_outreach.append({
                "app": r["app"],
                "category": r["category"],
                "blocker": r["blocker"],
                "gating_notes": r["gating_notes"],
                "website": r["evidence_url"]
            })
            
    patterns = {
        "total_apps": len(results),
        "auth_distribution": auth_distribution,
        "self_serve_distribution": self_serve_distribution,
        "blocker_distribution": blocker_distribution,
        "buildability_distribution": buildability_distribution,
        "category_analysis": category_data,
        "easy_wins": {
            "count": len(easy_wins),
            "apps": easy_wins
        },
        "needs_outreach": {
            "count": len(needs_outreach),
            "apps": needs_outreach
        }
    }
    
    with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(patterns, f, indent=2, ensure_ascii=False)
        
    print(f"Patterns file written successfully to {PATTERNS_FILE}")
    print(f"- Easy Wins found: {len(easy_wins)}")
    print(f"- Gated Outreach needed: {len(needs_outreach)}")

if __name__ == "__main__":
    main()
