from fastapi import APIRouter, HTTPException
from supabase import create_client
import os

router = APIRouter()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@router.get("/checkuser")
def check_user(id: str = None, email: str = None):
    query = supabase.table("users").select("*")
    if id:
        query = query.eq("id", id)
    if email:
        query = query.eq("email", email)
    response = query.execute()
    users = response.data or []
    if not users:
        raise HTTPException(status_code=404, detail="User not found")
    return users[0]
