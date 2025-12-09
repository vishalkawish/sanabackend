import os
import json
from datetime import datetime, timezone
from fastapi import APIRouter
from supabase import create_client
import random
import traceback

router = APIRouter()

# -------------------------
# Supabase setup
# -------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

print("✅ SUPABASE_URL exists:", bool(SUPABASE_URL))
print("✅ SUPABASE_KEY exists:", bool(SUPABASE_KEY))

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# Astrology constants
# -------------------------
PLANET_WEIGHTS = {
    "Sun": 1.0, "Moon": 1.5, "Venus": 2.0, "Mars": 1.8,
    "Mercury": 1.0, "Jupiter": 1.2, "Saturn": 1.5,
    "North Node": 2.0, "South Node": 2.0
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

def safe_json(val):
    try:
        if isinstance(val, str):
            val = json.loads(val)
        if isinstance(val, str):
            val = json.loads(val)
        return val if isinstance(val, dict) else {}
    except:
        return {}

# -------------------------
# Compatibility Engine
# -------------------------
def deep_compatibility(user_chart, crush_chart):
    print("🔍 [compat] started")

    user_chart = safe_json(user_chart)
    crush_chart = safe_json(crush_chart)

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

    # ✅ SAFE elemental match bonus
    u_sign = user_chart.get("ascendant", {}).get("sign")
    c_sign = crush_chart.get("ascendant", {}).get("sign")

    print("🔍 [element] u_sign:", u_sign, "c_sign:", c_sign)

    if u_sign and c_sign:
        ue = SIGN_ELEMENTS.get(u_sign)
        ce = SIGN_ELEMENTS.get(c_sign)
        if ue and ce and ue == ce:
            print("✅ [element] bonus applied:", ue)
            total_score += ELEMENT_SCORE[ue]

    if total_weight == 0:
        return 0

    percent = max(0, min(100, round((total_score / (total_weight * 10)) * 100)))
    print("✅ [compat] percent:", percent)
    return percent

def classify_connection(score):
    if score >= 85:
        return "soulmate"
    if score >= 30:
        return "twin_flame"
    return "karmic"

# -------------------------
# Supabase helpers ✅ SAFE + LOGGED
# -------------------------
def fetch_user(uid: str):
    try:
        print("🟢 [fetch_user] id:", uid)

        res = supabase.table("users").select("*").eq("id", uid).execute()
        print("✅ [fetch_user] raw:", res)

        if not res or not res.data:
            print("⚠️ [fetch_user] not found")
            return None

        print("✅ [fetch_user] found")
        return res.data[0]

    except Exception as e:
        print("🔥 [fetch_user] CRASH:", repr(e))
        traceback.print_exc()
        return None


def fetch_all_users():
    try:
        print("🟢 [fetch_all_users]")
        res = supabase.table("users").select("*").execute()

        if not res or not res.data:
            print("⚠️ [fetch_all_users] empty")
            return []

        print("✅ [fetch_all_users] count:", len(res.data))
        return res.data

    except Exception as e:
        print("🔥 [fetch_all_users] CRASH:", repr(e))
        traceback.print_exc()
        return []

# -------------------------
# API Route ✅ FULL DEBUG SAFE + TIMEZONE SAFE
# -------------------------
@router.get("/soul_of_anlasana_2_1/{user_id}")
def soul_of_anlasana(user_id: str):

    print("\n🚀 [API HIT] user_id:", user_id)

    try:
        user = fetch_user(user_id)

        if not user:
            return {"user_id": user_id, "matches": []}

        target_chart = user.get("chart")
        target_gender = user.get("gender")
        target_age = user.get("age")

        print("✅ [user] gender:", target_gender, "age:", target_age)

        if not target_chart or not target_gender or target_age is None:
            return {"user_id": user_id, "matches": []}

        all_users = fetch_all_users()

        matches, seen = [], set()

        for other in all_users:
            try:
                if other.get("id") == user_id:
                    continue
                if other.get("gender") == target_gender:
                    continue
                if not other.get("chart"):
                    continue
                if not other.get("age") or other.get("age") < 18:
                    continue
                if other.get("name") in seen:
                    continue

                seen.add(other.get("name"))

                score = deep_compatibility(target_chart, other.get("chart"))
                ctype = classify_connection(score)

                matches.append({
                    "sana_id": other.get("sana_id"),
                    "id": other.get("id"),
                    "name": other.get("name"),
                    "profilePicUrl": other.get("profilePicUrl"),
                    "type": ctype,
                    "match_percent": score,
                    "age": other.get("age"),
                    "birthdate": other.get("birthdate"),
                    "birthplace": other.get("birthplace"),
                    "last_active": other.get("last_active")
                })

            except Exception as loop_err:
                print("⚠️ [loop user skipped]:", repr(loop_err))
                traceback.print_exc()

        # ✅ TIMEZONE-SAFE SORTING
        for m in matches:
            last_active = m.get("last_active")
            try:
                dt = datetime.fromisoformat(last_active)

                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                m["_last_active_dt"] = dt

            except:
                m["_last_active_dt"] = datetime.min.replace(tzinfo=timezone.utc)

        matches.sort(key=lambda x: x["_last_active_dt"], reverse=True)

        top_match = matches[0] if matches else None

        print("✅ [API DONE] matches:", len(matches))

        return {
            "user_id": user_id,
            "summary": {
                "top_match": top_match
            },
            "matches": matches
        }

    except Exception as e:
        print("🔥🔥🔥 [API CRASH]:", repr(e))
        traceback.print_exc()
        return {
            "user_id": user_id,
            "error": str(e),
            "type": str(type(e))
        }
