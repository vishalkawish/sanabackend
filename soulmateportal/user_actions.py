from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client
import os
from datetime import datetime

router = APIRouter()

# Supabase config
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing!")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

class UserAction(BaseModel):
    user_id: str
    target_user_id: str
    action: str

@router.post("/user_action/")
def record_action(data: UserAction):
    user_id = data.user_id
    target_user_id = data.target_user_id
    action = data.action

    if action not in ["skip", "connect"]:
        raise HTTPException(status_code=400, detail="Invalid action")

    existing = supabase.table("user_actions")\
        .select("*")\
        .eq("user_id", target_user_id)\
        .eq("target_user_id", user_id)\
        .eq("action", "connect")\
        .execute()

    is_match = False
    if existing.data and action == "connect":
        is_match = True
        supabase.table("user_actions")\
            .update({"action": "matched", "updated_at": datetime.utcnow()})\
            .eq("user_id", target_user_id)\
            .eq("target_user_id", user_id)\
            .execute()

    supabase.table("user_actions").insert({
        "user_id": user_id,
        "target_user_id": target_user_id,
        "action": "matched" if is_match else action,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }).execute()

    return {"status": "ok", "matched": is_match}
