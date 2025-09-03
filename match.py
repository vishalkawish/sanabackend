# match.py
import os
import json
import requests
from fastapi import APIRouter, HTTPException
from pathlib import Path
from compatibility import calculate_compatibility_score

router = APIRouter()

USER_CHART_DIR = Path("./user_charts")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing! Set SUPABASE_URL and SUPABASE_KEY in .env")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

def get_best_matches(user_id: str, top_n: int = 5):
    # 1️⃣ Fetch current user
    url = f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}&select=*"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200 or not resp.json():
        raise HTTPException(status_code=404, detail="User not found")

    current_user = resp.json()[0]
    user_name = current_user["name"]
    user_gender = current_user.get("gender", "").lower()

    # 2️⃣ Load user chart
    chart_file = USER_CHART_DIR / f"{user_name}.json"
    if not chart_file.exists():
        raise HTTPException(status_code=404, detail="User chart not found")
    with open(chart_file, "r") as f:
        user_chart = json.load(f)

    # 3️⃣ Fetch all users
    all_users_resp = requests.get(f"{SUPABASE_URL}/rest/v1/users?select=*", headers=HEADERS)
    if all_users_resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch users")

    users = all_users_resp.json()

    # 4️⃣ Compatibility + gender filter
    matches = []
    for u in users:
        if u["id"] == user_id:
            continue

        other_gender = u.get("gender", "").lower()

        # ✅ Gender filtering
        if user_gender == "male" and other_gender != "female":
            continue
        if user_gender == "female" and other_gender != "male":
            continue

        chart_path = USER_CHART_DIR / f"{u['name']}.json"
        if not chart_path.exists():
            continue

        with open(chart_path, "r") as f:
            crush_chart = json.load(f)

        score = calculate_compatibility_score(user_chart, crush_chart)
        matches.append({
            "id": u["id"],
            "name": u["name"],
            "gender": u.get("gender", "unknown"),
            "score": score
        })

    # 5️⃣ Sort & return
    matches_sorted = sorted(matches, key=lambda x: x["score"], reverse=True)[:top_n]
    return matches_sorted

@router.get("/matches/{user_id}")
def api_get_matches(user_id: str, top_n: int = 5):
    matches = get_best_matches(user_id, top_n)
    if not matches:
        raise HTTPException(status_code=404, detail="No matches found")
    return {"user_id": user_id, "matches": matches}
