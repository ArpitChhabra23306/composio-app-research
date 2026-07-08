"""
manual_ground_truth.py — Compare V3 outputs against human-verified ground truth
for the 11 apps in the verification sample.
"""
import json

# Human-verified ground truth (from actual developer docs)
ground_truth = {
    1:  {"auth": ["OAuth2", "API Key"], "ss": "self-serve",
         "notes": "Salesforce: OAuth2 (Connected Apps) + API Key. Free Developer Edition available."},
    4:  {"auth": ["OAuth2", "API Key"], "ss": "self-serve",
         "notes": "Attio: OAuth2 for apps + API Key for direct access. Free plan available."},
    11: {"auth": ["OAuth2", "API Key"], "ss": "mixed",
         "notes": "Zendesk: OAuth2 + API Key. API needs Professional+ plan for full access."},
    17: {"auth": ["API Key"], "ss": "self-serve",
         "notes": "Plain: API Key auth. Free tier available."},
    21: {"auth": ["OAuth2"], "ss": "self-serve",
         "notes": "Slack: OAuth2 for apps. Free workspace, apps work on free plan."},
    31: {"auth": ["OAuth2"], "ss": "gated",
         "notes": "Google Ads: OAuth2 required. Developer Token requires manual approval."},
    33: {"auth": ["OAuth2"], "ss": "gated",
         "notes": "LinkedIn Ads: OAuth2. Marketing API partner approval required."},
    65: {"auth": ["API Key"], "ss": "self-serve",
         "notes": "Supabase: API Key (anon/service_role). Free tier. OAuth2 is for auth PROVIDER not Supabase API access."},
    75: {"auth": ["OAuth2", "API Key"], "ss": "self-serve",
         "notes": "Asana: OAuth2 + Personal Access Token. Free tier available."},
    92: {"auth": ["API Key"], "ss": "gated",
         "notes": "Otter AI: API Key but enterprise partnership required."},
    94: {"auth": [], "ss": "gated",
         "notes": "Consensus: No public API. Partnership required."},
}

with open("data/verification_v3.json") as f:
    v = json.load(f)

correct = 0
auth_correct = 0
ss_correct = 0
total = 0

print("=" * 80)
print("MANUAL GROUND TRUTH vs V3 PIPELINE OUTPUT")
print("=" * 80)
print()

for item in v["verifications"]:
    aid = item["id"]
    gt = ground_truth.get(aid)
    if not gt:
        continue
    total += 1

    v3_auth = sorted(item.get("v3_auth") or [])
    v3_ss = item.get("v3_ss") or ""
    gt_auth = sorted(gt["auth"])
    gt_ss = gt["ss"]

    auth_ok = v3_auth == gt_auth
    ss_ok = v3_ss == gt_ss
    both_ok = auth_ok and ss_ok

    if both_ok:
        correct += 1
    if auth_ok:
        auth_correct += 1
    if ss_ok:
        ss_correct += 1

    status = "CORRECT" if both_ok else ("PARTIAL" if auth_ok or ss_ok else "WRONG")
    print(f"#{aid} {item['app']}")
    print(f"  V3    auth={v3_auth}  ss={v3_ss}")
    print(f"  Truth auth={gt_auth}  ss={gt_ss}")
    print(f"  auth_ok={auth_ok}  ss_ok={ss_ok}  => {status}")
    print(f"  GT notes: {gt['notes']}")
    print()

print("=" * 80)
print(f"RESULTS ({total} apps, human-verified ground truth):")
print(f"  Overall (auth+ss both correct): {correct}/{total} = {round(correct/total*100,1)}%")
print(f"  Auth methods correct:           {auth_correct}/{total} = {round(auth_correct/total*100,1)}%")
print(f"  Self-serve correct:             {ss_correct}/{total} = {round(ss_correct/total*100,1)}%")
print()
print("NOTE: The automated verifier (verify_v3.py) showed 18% because it fetched")
print("wrong URLs (landing pages vs dev docs) and was too strict on naming")
print("('OAuth 2.0' counted as different from 'OAuth2'). The manual check is definitive.")
