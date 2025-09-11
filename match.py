import os
import random
import json
from datetime import datetime, date
from fastapi import APIRouter, HTTPException
from supabase import create_client
from charts import calculate_chart
from compatibility import calculate_compatibility_score
from fetchuser import fetch_user_from_supabase_by_username
from helpers import generate_chart_for_user

router = APIRouter()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing!")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
USER_CHART_DIR = os.environ.get("USER_CHART_DIR", "./user_charts")


# -----------------------------
# Utility: calculate age
# -----------------------------
def calculate_age(birthdate_str: str):
    if not birthdate_str:
        return None
    try:
        if len(birthdate_str) == 10:
            birthdate = datetime.strptime(birthdate_str, "%Y-%m-%d").date()
        else:
            birthdate = datetime.fromisoformat(birthdate_str).date()

        today = date.today()
        return today.year - birthdate.year - (
            (today.month, today.day) < (birthdate.month, birthdate.day)
        )
    except Exception:
        return None


# -----------------------------
# Get best matches
# -----------------------------
def get_best_matches(user_id: str, top_n: int = None):
    try:
        response = supabase.table("users").select("*").execute()
        users = response.data or []
    except Exception:
        return []

    current_user = next((u for u in users if u.get("id") == user_id), None)
    if not current_user:
        return []

    # Ensure current user's chart exists
    user_chart_path = os.path.join(USER_CHART_DIR, f"{current_user['name']}.json")
    user_chart = None
    if not os.path.exists(user_chart_path):
        generate_chart_for_user(current_user["id"])
    if os.path.exists(user_chart_path):
        with open(user_chart_path, "r") as f:
            user_chart = json.load(f)

    matches = []
    for u in users:
        try:
            if u.get("id") == user_id:
                continue
            if not u.get("gender") or not u.get("birthdate"):
                continue

            # Simple opposite-gender filter
            if current_user.get("gender") == "Male" and u.get("gender") != "Female":
                continue
            if current_user.get("gender") == "Female" and u.get("gender") != "Male":
                continue

            age = calculate_age(u.get("birthdate"))
            if age is None or age < 18:
                continue

            # Load crush chart
            crush_chart_path = os.path.join(USER_CHART_DIR, f"{u['name']}.json")
            crush_chart = None
            if not os.path.exists(crush_chart_path):
                generate_chart_for_user(u["id"])
            if os.path.exists(crush_chart_path):
                with open(crush_chart_path, "r") as f:
                    crush_chart = json.load(f)

            # Calculate compatibility score
            score = 0
            if user_chart and crush_chart:
                try:
                    score = calculate_compatibility_score(user_chart, crush_chart)
                except Exception:
                    score = 0

            matches.append({
                "id": u.get("id"),
                "name": u.get("name"),
                "gender": u.get("gender"),
                "age": age,
                "profile_pic_url": u.get("profile_pic_url"),
                "compatibility_score": score,
                "birthdate": u.get("birthdate"),
                "birthtime": u.get("birthtime"),
                "birthplace": u.get("birthplace"),
                "email": u.get("email"),
                "created_at": u.get("created_at"),
                "updated_at": u.get("updated_at"),
            })
        except Exception:
            continue

    random.shuffle(matches)
    return matches[:top_n]


# -----------------------------
# API Endpoint
# -----------------------------
def api_get_matches(user_id: str):
    matches = get_best_matches(user_id, top_n=None)  # top_n=None = all matches
    if not matches:
        raise HTTPException(status_code=404, detail="No matches found")
    return {"user_id": user_id, "matches": matches}
