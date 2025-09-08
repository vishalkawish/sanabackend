from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client
import os

router = APIRouter()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

class CheckUserPayload(BaseModel):
    id: str = None
    email: str = None

@router.post("/checkuser")
def check_user(payload: CheckUserPayload):
    if not payload.id and not payload.email:
        raise HTTPException(status_code=400, detail="id or email required")

    query = supabase.table("users").select("*")

    if payload.id:
        query = query.eq("id", payload.id)
    if payload.email:
        query = query.eq("email", payload.email)

    response = query.execute()
    users = response.data or []

    if not users:
        raise HTTPException(status_code=404, detail="User not found")

    # ✅ Return single object instead of list
    return users[0]


# -----------------------------
# Function needed for match.py
# -----------------------------
def fetch_user_from_supabase_by_username(username: str):
    """Fetch a user by username from Supabase (used in match.py)."""
    if not username:
        return None

    query = supabase.table("users").select("*").eq("username", username)
    response = query.execute()
    users = response.data or []
    return users[0] if users else None
