from datetime import datetime, date
from fastapi import APIRouter
from supabase import create_client
import os

router = APIRouter()

# Supabase config
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing!")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def calculate_age(birthdate_str: str):
    """Calculate age from YYYY-MM-DD or ISO string."""
    if not birthdate_str:
        return None
    try:
        if len(birthdate_str) == 10:  # "YYYY-MM-DD"
            birthdate = datetime.strptime(birthdate_str, "%Y-%m-%d").date()
        else:
            birthdate = datetime.fromisoformat(birthdate_str).date()
        today = date.today()
        return today.year - birthdate.year - (
            (today.month, today.day) < (birthdate.month, birthdate.day)
        )
    except Exception:
        return None


def get_best_matches(user_id: str, top_n: int = 5):
    try:
        response = supabase.table("users").select("*").execute()
        users = response.data or []
    except Exception:
        return []

    current_user = next((u for u in users if u.get("id") == user_id), None)
    if not current_user:
        return []

    matches = []
    for u in users:
        try:
            if u.get("id") == user_id:
                continue

            # Ignore if critical data missing
            if not u.get("gender") or not u.get("birthdate"):
                continue

            # Gender filter (opposite only)
            if current_user.get("gender") == "Male" and u.get("gender") != "Female":
                continue
            if current_user.get("gender") == "Female" and u.get("gender") != "Male":
                continue

            age = calculate_age(u.get("birthdate"))
            if age is None:
                continue

            # Append only necessary public fields
            matches.append({
                "id": u.get("id"),
                "name": u.get("name"),
                "gender": u.get("gender"),
                "age": age,
                "birthdate": u.get("birthdate"),
                "birthtime": u.get("birthtime"),
                "birthplace": u.get("birthplace"),
                "profile_pic_url": u.get("profile_pic_url")
            })

        except Exception:
            continue

    return matches[:top_n]


@router.get("/matches/{user_id}")
def api_get_matches(user_id: str, top_n: int = 5):
    try:
        matches = get_best_matches(user_id, top_n)
        return {
            "user_id": user_id,
            "matches": matches  # Array of public match objects
        }
    except Exception as e:
        return {
            "error": str(e),
            "user_id": user_id,
            "matches": []
        }
