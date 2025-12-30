import os
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from supabase import create_client
from openai import OpenAI
import random
import traceback
import asyncio

router = APIRouter()

# -------------------------
# Setup
# -------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

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
    if not val:
        return {}
    if isinstance(val, dict):
        return val
    try:
        if isinstance(val, str):
            # Try to parse if it's a string, removing possible outer quotes if it was double-serialized
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            val = json.loads(val)
        return val if isinstance(val, dict) else {}
    except:
        return {}

def decrypt_if_needed(val):
    # This is a placeholder - usually handled by frontend or storage layer
    return val

# -------------------------
# Compatibility Engine
# -------------------------
def deep_compatibility(user_chart, crush_chart):
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

    u_sign = user_chart.get("ascendant", {}).get("sign")
    c_sign = crush_chart.get("ascendant", {}).get("sign")

    if u_sign and c_sign:
        ue = SIGN_ELEMENTS.get(u_sign)
        ce = SIGN_ELEMENTS.get(c_sign)
        if ue and ce and ue == ce:
            total_score += ELEMENT_SCORE[ue]

    if total_weight == 0:
        return 0

    return max(0, min(100, round((total_score / (total_weight * 10)) * 100)))

def classify_connection(score):
    if score >= 85: return "soulmate"
    if score >= 30: return "twin_flame"
    return "karmic"

# -------------------------
# Supabase helpers
# -------------------------
def fetch_user(uid: str):
    res = supabase.table("users").select("*").eq("id", uid).execute()
    return res.data[0] if res.data else None

def fetch_top_psych_matches(vector: list, limit: int = 100):
    try:
        res = supabase.rpc("match_users", {
            "query_vector": vector,
            "match_limit": limit
        }).execute()
        return res.data or []
    except Exception as e:
        print("🔥 [vector search] failed:", e)
        # Fallback to general fetch if RPC fails
        res = supabase.table("users").select("*").limit(limit).execute()
        return res.data or []

# -------------------------
# API Routes
# -------------------------

@router.get("/soul_of_anlasana_2_1/{user_id}")
async def soul_of_anlasana(user_id: str):
    try:
        user = fetch_user(user_id)
        if not user:
            print(f"❌ [Matching] User {user_id} not found in database")
            return {"user_id": user_id, "matches": []}

        target_chart = user.get("chart")
        target_gender = user.get("gender")
        target_vector = user.get("psych_vector")

        print(f"🔍 [Matching] User {user_id}: gender={target_gender}, has_chart={bool(target_chart)}, has_vector={bool(target_vector)}")

        if not target_chart or not target_gender:
            print(f"❌ [Matching] User missing required fields - chart: {bool(target_chart)}, gender: {bool(target_gender)}")
            return {"user_id": user_id, "matches": []}

        # Quality matching: Start with top 100 psychological matches
        if target_vector:
            # RPC returns only IDs, we need to fetch full user data
            match_results = fetch_top_psych_matches(target_vector, 100)
            print(f"📊 [Matching] RPC returned {len(match_results)} results")
            if match_results and len(match_results) > 0:
                print(f"🔍 [Matching] First RPC result keys: {list(match_results[0].keys())}")
            else:
                print(f"🔍 [Matching] No results from RPC")
            
            # Extract IDs and fetch full user data including charts
            if match_results:
                user_ids = [m.get("id") for m in match_results if m.get("id")]
                print(f"🔍 [Matching] Extracted {len(user_ids)} user IDs from RPC")
                
                if user_ids:
                    print(f"🔍 [Matching] Re-fetching full data for {len(user_ids)} users...")
                    res = supabase.table("users").select("*").in_("id", user_ids).execute()
                    candidates = res.data or []
                    print(f"✅ [Matching] Successfully fetched {len(candidates)} full user records")
                    if candidates and len(candidates) > 0:
                        print(f"🔍 [Matching] First candidate keys: {list(candidates[0].keys())}")
                    else:
                        print(f"⚠️ [Matching] No candidates returned from fetch")
                else:
                    print(f"⚠️ [Matching] No user IDs extracted, using empty candidates")
                    candidates = []
            else:
                print(f"⚠️ [Matching] No match results from RPC, using empty candidates")
                candidates = []
        else:
            print(f"⚠️ [Matching] No psych_vector, using general query")
            res = supabase.table("users").select("*").limit(100).execute()
            candidates = res.data or []
            print(f"📊 [Matching] Found {len(candidates)} candidates via general query")

        matches, seen = [], set()
        skipped_reasons = {
            "same_user": 0,
            "same_gender": 0,
            "no_chart": 0,
            "under_18": 0,
            "duplicate_name": 0
        }
        
        # Debug: Check first few candidates to see what chart data looks like
        for i, candidate in enumerate(candidates[:3]):
            chart_data = candidate.get("chart")
            print(f"🔎 [Debug] Candidate {i+1}: id={candidate.get('id')[:10]}..., has_chart_field={chart_data is not None}, chart_type={type(chart_data)}, chart_value_preview={str(chart_data)[:100] if chart_data else 'None'}")
        
        for other in candidates:
            if other.get("id") == user_id: 
                skipped_reasons["same_user"] += 1
                continue
            if other.get("gender") == target_gender: 
                skipped_reasons["same_gender"] += 1
                continue
            
            chart_raw = other.get("chart")
            if not chart_raw:
                skipped_reasons["no_chart"] += 1
                continue
            
            # Try to parse the chart to see if it's valid
            try:
                chart_parsed = safe_json(chart_raw)
                if not chart_parsed or not chart_parsed.get("planets"):
                    print(f"⚠️ [Debug] Chart exists but is empty/invalid for user {other.get('id')[:10]}... - chart_parsed: {chart_parsed}")
                    skipped_reasons["no_chart"] += 1
                    continue
            except Exception as e:
                print(f"❌ [Debug] Chart parsing failed for user {other.get('id')[:10]}... - error: {e}")
                skipped_reasons["no_chart"] += 1
                continue
            
            if (other.get("age") or 0) < 18: 
                skipped_reasons["under_18"] += 1
                continue
            if other.get("name") in seen: 
                skipped_reasons["duplicate_name"] += 1
                continue

            seen.add(other.get("name"))

            astrological_score = deep_compatibility(target_chart, other.get("chart"))
            ctype = classify_connection(astrological_score)

            matches.append({
                "id": other.get("id"),
                "sana_id": other.get("sana_id"),
                "name": other.get("name"),
                "profilePicUrl": other.get("profilePicUrl"),
                "type": ctype,
                "match_percent": astrological_score,
                "age": other.get("age"),
                "birthdate": other.get("birthdate"),
                "birthplace": other.get("birthplace"),
                "last_active": other.get("last_active")
            })

        print(f"🚫 [Matching] Skipped: {skipped_reasons}")
        print(f"✅ [Matching] Found {len(matches)} valid matches before sorting")

        # Sort by match percent and limit to top 30 for quality
        matches.sort(key=lambda x: x["match_percent"], reverse=True)
        final_matches = matches[:30]

        print(f"🎯 [Matching] Returning {len(final_matches)} final matches for user {user_id}")

        return {
            "user_id": user_id,
            "matches": final_matches
        }

    except Exception as e:
        traceback.print_exc()
        print(f"❌ [Matching] Error: {str(e)}")
        return {"user_id": user_id, "error": str(e)}

@router.get("/sana/advice/{user_id}/{target_id}")
async def get_sana_advice(user_id: str, target_id: str):
    try:
        u1 = fetch_user(user_id)
        u2 = fetch_user(target_id)
        
        if not u1 or not u2:
            raise HTTPException(status_code=404, detail="User not found")

        p1 = safe_json(u1.get("psych_map"))
        p2 = safe_json(u2.get("psych_map"))
        name1 = u1.get("name")
        name2 = u2.get("name")


        # Astrology context for GPT
        score = deep_compatibility(u1.get("chart"), u2.get("chart"))

        prompt = f"""
        Analyze the psychological compatibility between two users.
        
        {name1} Traits: {json.dumps(p1)}
        {name2} Traits: {json.dumps(p2)}
        Astrological Compatibility: {score}%
        
        Rules:
        1. Reply in one line if they are good fit or not.
        2. Highlight their common interests and traits.. Maximum 4 interests or traits.
        3. Return STRICT JSON: {{"advice": "...", "common_traits": "..."}}
        """

        def _call_gpt():
            return openai_client.chat.completions.create(
                model="gpt-5-nano",
                messages=[{"role": "system", "content": "You are Sana, a warm AI matchmaker."},
                          {"role": "user", "content": prompt}]
            )

        resp = await asyncio.to_thread(_call_gpt)
        content = resp.choices[0].message.content
        data = json.loads(content[content.find("{"):content.rfind("}")+1])

        return {
            "target_id": target_id,
            "advice": data.get("advice"),
            "astrological_score": score,
            "common_traits": data.get("common_traits")
        }

    except Exception as e:
        print(f"Advice Error: {e}")
        return {
            "advice": "Sana is sensing a unique connection here. Focus on your shared values.",
        }
