from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import Optional
from supabase import create_client
import os
from datetime import datetime, timezone


router = APIRouter()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

class CheckUserPayload(BaseModel):
    id: Optional[str] = None
    email: Optional[str] = None

@router.post("/checkuser")
async def check_user(
    request: Request,
    id: Optional[str] = Query(None),
    email: Optional[str] = Query(None)
):
    """
    Fetch user by JSON body or query params.
    Returns single user object or 404 if not found.
    """

    # Attempt to parse JSON body
    try:
        body = await request.json()
        id = body.get("id", id)
        email = body.get("email", email)
    except Exception:
        pass  # No JSON body sent → fallback to query params

    if not id and not email:
        raise HTTPException(status_code=400, detail="id or email required")

    query = supabase.table("users").select("*")
    if id:
        query = query.eq("id", id)
    if email:
        query = query.eq("email", email)

    response = query.execute()
    users = response.data or []

    try:
        supabase.table("users").update({
            "last_active": datetime.now(timezone.utc).isoformat()
        }).eq("id", user["id"]).execute()
    except Exception as e:
        print(f"⚠️ Failed to update last_active: {e}")

    if not users:
        raise HTTPException(status_code=404, detail="User not found")

    return users[0]  # Return single object instead of list


# -----------------------------
# Helper function for match.py
# -----------------------------
def fetch_user_from_supabase_by_username(username: str):
    """Fetch a user by username from Supabase (used in match.py)."""
    if not username:
        return None

    query = supabase.table("users").select("*").eq("username", username)
    response = query.execute()
    users = response.data or []
    return users[0] if users else None
