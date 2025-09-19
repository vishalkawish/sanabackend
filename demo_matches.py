import random
from fastapi import APIRouter
from supabase import create_client
import os
import json

router = APIRouter()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# Supabase helpers
# -------------------------
def fetch_user(uid: str):
    res = supabase.table("users").select("*").eq("id", uid).maybe_single().execute()
    return res.data

def fetch_all_users():
    res = supabase.table("users").select("*").execute()
    return res.data or []

# -------------------------
# Safe JSON/dict parser
# -------------------------
def parse_chart(chart):
    if isinstance(chart, str):
        try:
            return json.loads(chart)
        except json.JSONDecodeError:
            return {}
    elif isinstance(chart, dict):
        return chart
    return {}

# -------------------------
# Compatibility calculation
# -------------------------
def calculate_compatibility_score(user_chart, crush_chart):
    score = 50
    pairs = [
        ("Sun", "Moon"),
        ("Moon", "Moon"),
        ("Venus", "Mars"),
        ("Mars", "Venus"),
        ("Sun", "Venus"),
        ("Moon", "Venus"),
    ]

    user_planets = user_chart.get("planets", {}) if isinstance(user_chart, dict) else {}
    crush_planets = crush_chart.get("planets", {}) if isinstance(crush_chart, dict) else {}

    for u, c in pairs:
        user_planet = user_planets.get(u)
        crush_planet = crush_planets.get(c)
        if not user_planet or not crush_planet:
            continue

        diff = abs(user_planet.get("longitude", 0) - crush_planet.get("longitude", 0)) % 360
        if diff > 180:
            diff = 360 - diff

        if diff < 5:
            score += 10
        elif diff < 15:
            score += 6
        elif abs(diff - 60) < 5:
            score += 4
        elif abs(diff - 120) < 5:
            score += 5
        elif abs(diff - 90) < 5:
            score -= 3
        elif abs(diff - 180) < 5:
            score -= 5

    # Rescale raw score (50–100) to premium range (76–98)
    min_raw, max_raw = 50, 100
    min_premium, max_premium = 76, 98
    score = min_premium + (score - min_raw) * (max_premium - min_premium) / (max_raw - min_raw)
    return round(score)

# -------------------------
# Random gender-based match with score
# -------------------------
@router.get("/random_match/{user_id}")
def random_match(user_id: str, count: int = 3):
    user = fetch_user(user_id)
    if not user:
        return {"user_id": user_id, "matches": []}

    user_gender = (user.get("gender") or "").strip().lower()
    target_chart = parse_chart(user.get("chart"))
    all_users = fetch_all_users()

    # Filter opposite gender only and exclude self
    if user_gender == "male":
        candidates = [u for u in all_users 
                      if (u.get("gender") or "").strip().lower() == "female" 
                      and u.get("id") != user_id]
    elif user_gender == "female":
        candidates = [u for u in all_users 
                      if (u.get("gender") or "").strip().lower() == "male" 
                      and u.get("id") != user_id]
    else:
        candidates = []

    if not candidates:
        return {"user_id": user_id, "matches": []}

    matches = random.sample(candidates, min(count, len(candidates)))

    result = []
    for match in matches:
        crush_chart = parse_chart(match.get("chart"))
        match_percent = calculate_compatibility_score(target_chart, crush_chart)
        result.append({
            "id": match.get("id"),
            "name": match.get("name"),
            "match_percent": match_percent,
            "url": match.get("profile_pic_url")
        })

    return {"user_id": user_id, "matches": result}
