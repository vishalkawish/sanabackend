from datetime import datetime, date
from fastapi import APIRouter, HTTPException
from supabase import create_client
import os
from compatibility import calculate_compatibility_score

router = APIRouter()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing!")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def calculate_age(birthdate_str: str) -> int:
    """Calculate age from YYYY-MM-DD string."""
    try:
        birthdate = datetime.strptime(birthdate_str, "%Y-%m-%d").date()
        today = date.today()
        return today.year - birthdate.year - (
            (today.month, today.day) < (birthdate.month, birthdate.day)
        )
    except Exception:
        return None


def get_best_matches(user_id: str, top_n: int = 5):
    # Fetch all users
    response = supabase.table("users").select("*").execute()
    users = response.data

    # Find current user
    current_user = next((u for u in users if u["id"] == user_id), None)
    if not current_user:
        return []

    matches = []
    for u in users:
        if u["id"] == user_id:
            continue

        # Gender filter (opposite only)
        if current_user.get("gender") == "Male" and u.get("gender") != "Female":
            continue
        if current_user.get("gender") == "Female" and u.get("gender") != "Male":
            continue

        # Compatibility score
        score = calculate_compatibility_score(current_user, u)

        matches.append({
            "id": u["id"],
            "name": u.get("name"),
            "gender": u.get("gender"),
            "age": calculate_age(u.get("birthdate")),
            "profile_pic_url": u.get("profile_pic_url"),
            "score": score,
        })

    # Sort by score (desc) and return top_n
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:top_n]


@router.get("/matches/{user_id}")
def api_get_matches(user_id: str, top_n: int = 5):
    matches = get_best_matches(user_id, top_n)
    return {"user_id": user_id, "matches": matches}
