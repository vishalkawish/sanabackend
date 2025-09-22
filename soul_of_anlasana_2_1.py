import os
import json
from datetime import datetime
from fastapi import APIRouter
from supabase import create_client

router = APIRouter()

# -------------------------
# Supabase setup
# -------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# Astrology constants
# -------------------------
PLANET_WEIGHTS = {
    "Sun": 1.0,
    "Moon": 1.5,
    "Venus": 2.0,
    "Mars": 1.8,
    "Mercury": 1.0,
    "Jupiter": 1.2,
    "Saturn": 1.5,
    "North Node": 2.0,
    "South Node": 2.0
}

HOUSE_IMPORTANCE = {5: 1.5, 7: 2.0, 8: 1.8}

ASPECTS = {
    "conjunction": {"angle": 0, "orb": 10, "score": 10},
    "sextile": {"angle": 60, "orb": 5, "score": 5},
    "square": {"angle": 90, "orb": 6, "score": -5},
    "trine": {"angle": 120, "orb": 8, "score": 7},
    "opposition": {"angle": 180, "orb": 8, "score": -8},
}

SIGN_ELEMENTS = {
    "Aries": "Fire", "Leo": "Fire", "Sagittarius": "Fire",
    "Taurus": "Earth", "Virgo": "Earth", "Capricorn": "Earth",
    "Gemini": "Air", "Libra": "Air", "Aquarius": "Air",
    "Cancer": "Water", "Scorpio": "Water", "Pisces": "Water"
}

ELEMENT_SCORE = {"Fire": 5, "Earth": 5, "Air": 5, "Water": 5}

# -------------------------
# Helper functions
# -------------------------
def angle_diff(deg1, deg2):
    diff = abs(deg1 - deg2) % 360
    return diff if diff <= 180 else 360 - diff

def get_aspect_score(diff):
    for info in ASPECTS.values():
        if abs(diff - info["angle"]) <= info["orb"]:
            return info["score"]
    return 0

def moon_phase_bonus(u_chart, c_chart):
    u = u_chart.get("planets", {}).get("Moon")
    c = c_chart.get("planets", {}).get("Moon")
    if not u or not c:
        return 0
    diff = angle_diff(u.get("longitude", 0), c.get("longitude", 0))
    return 5 if diff <= 60 else (3 if diff <= 120 else 0)

def venus_mars_bonus(u_chart, c_chart):
    u_v = u_chart.get("planets", {}).get("Venus")
    u_m = u_chart.get("planets", {}).get("Mars")
    c_v = c_chart.get("planets", {}).get("Venus")
    c_m = c_chart.get("planets", {}).get("Mars")
    bonus = 0
    if u_v and c_m and angle_diff(u_v["longitude"], c_m["longitude"]) <= 30:
        bonus += 5
    if c_v and u_m and angle_diff(c_v["longitude"], u_m["longitude"]) <= 30:
        bonus += 5
    return bonus

def nodal_bonus(u_chart, c_chart):
    u_n = u_chart.get("planets", {}).get("North Node")
    u_s = u_chart.get("planets", {}).get("South Node")
    c_n = c_chart.get("planets", {}).get("North Node")
    c_s = c_chart.get("planets", {}).get("South Node")
    bonus = 0
    if u_n and c_s and angle_diff(u_n["longitude"], c_s["longitude"]) <= 15:
        bonus += 7
    if c_n and u_s and angle_diff(c_n["longitude"], u_s["longitude"]) <= 15:
        bonus += 7
    return bonus

def calc_life_path(birthdate_str):
    try:
        date = datetime.strptime(birthdate_str, "%Y-%m-%d")
        total = sum(int(d) for d in date.strftime("%Y%m%d"))
        while total > 9:
            total = sum(int(d) for d in str(total))
        return total
    except:
        return None

def life_path_bonus(u_chart, c_chart):
    u_lp = calc_life_path(u_chart.get("birthdate"))
    c_lp = calc_life_path(c_chart.get("birthdate"))
    if u_lp is None or c_lp is None:
        return 0
    diff = abs(u_lp - c_lp)
    return 5 if diff == 0 else (3 if diff == 1 else (2 if diff == 2 else 0))

# -------------------------
# Core compatibility
# -------------------------
def deep_compatibility(user_chart, crush_chart):
    if isinstance(user_chart, str):
        user_chart = json.loads(user_chart)
    if isinstance(crush_chart, str):
        crush_chart = json.loads(crush_chart)

    u_planets = user_chart.get("planets", {})
    c_planets = crush_chart.get("planets", {})
    total_score = 0
    total_weight = 0

    for planet, weight in PLANET_WEIGHTS.items():
        u = u_planets.get(planet)
        c = c_planets.get(planet)
        if not u or not c:
            continue
        diff = angle_diff(u["longitude"], c["longitude"])
        aspect_score = get_aspect_score(diff)
        house_multiplier = HOUSE_IMPORTANCE.get(u.get("house"), 1.0)
        total_score += aspect_score * weight * house_multiplier
        total_weight += weight * house_multiplier

    # Elemental match bonus
    if u.get("sign") and c.get("sign"):
        ue = SIGN_ELEMENTS.get(u["sign"])
        ce = SIGN_ELEMENTS.get(c["sign"])
        if ue and ce and ue == ce:
            total_score += ELEMENT_SCORE[ue]

    # One-time bonuses
    total_score += moon_phase_bonus(user_chart, crush_chart)
    total_score += venus_mars_bonus(user_chart, crush_chart)
    total_score += nodal_bonus(user_chart, crush_chart)
    total_score += life_path_bonus(user_chart, crush_chart)

    if total_weight == 0:
        return 0

    match_percent = max(0, min(100, round((total_score / (total_weight * 10)) * 100)))
    return match_percent

def classify_connection(score):
    if score >= 85:
        return "soulmate"
    if score >= 70:
        return "twin_flame"
    return "karmic"

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
# API Route
# -------------------------
# -------------------------
# API Route with age filtering
# -------------------------
@router.get("/soul_of_anlasana_2_1/{user_id}")
def soul_of_anlasana(user_id: str):
    user = fetch_user(user_id)
    if not user:
        return {"user_id": user_id, "matches": []}

    target_chart = user.get("chart")
    target_gender = user.get("gender")
    target_age = user.get("age")  # fetch age from Supabase

    if not target_chart or not target_gender or target_age is None:
        return {"user_id": user_id, "matches": []}

    all_users = fetch_all_users()
    matches, seen = [], set()

    for other in all_users:
        if other.get("id") == user_id:
            continue
        if other.get("gender") == target_gender:
            continue
        if not other.get("chart"):
            continue
        if not other.get("age") or other.get("age") < 18:  # ✅ 18+ check
            continue
        if not other.get("phone_number"):  
            continue
        if other.get("name") in seen:
            continue

        # ✅ Age range ±7
        if abs(other.get("age") - target_age) > 7:
            continue

        seen.add(other.get("name"))

        score = deep_compatibility(target_chart, other.get("chart"))
        ctype = classify_connection(score)
        matches.append({
            "user_id": other.get("id"),
            "name": other.get("name"),
            "url": other.get("profile_pic_url"),
            "type": ctype,
            "match_percent": score,
            "age": other.get("age"),  # include age in response
            "number": other.get("phone_number")  # include phone number in response
        })

    matches.sort(key=lambda x: x["match_percent"], reverse=True)

    summary = {
        "total_matches": len(matches),
        "soulmates": len([m for m in matches if m["type"] == "soulmate"]),
        "twin_flames": len([m for m in matches if m["type"] == "twin_flame"]),
        "karmic": len([m for m in matches if m["type"] == "karmic"]),
        "top_match": matches[0] if matches else None
    }

    return {"user_id": user_id, "summary": summary, "matches": matches}

