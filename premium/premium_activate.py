
# 1️⃣ Load env first
from dotenv import load_dotenv
load_dotenv()
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client
from datetime import datetime, timedelta
import os

router = APIRouter()

# -------------------------
# Supabase setup
# -------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# Request model
# -------------------------
class PremiumRequest(BaseModel):
    user_id: str
    premium_type: str  # 'prelaunch' or 'launch'

# -------------------------
# Activate Premium endpoint
# -------------------------
@router.post("/activate")
def activate_premium(data: PremiumRequest):
    # 1️⃣ Fetch user data safely
    user_res = supabase.table("users").select("id, name, email").eq("id", data.user_id).maybe_single().execute()
    if not user_res or not getattr(user_res, "data", None):
        raise HTTPException(status_code=404, detail="User not found")
    user = user_res.data

    # 2️⃣ Check if already premium safely
    existing_res = supabase.table("premium_users").select("id").eq("user_id", data.user_id).maybe_single().execute()
    if existing_res and getattr(existing_res, "data", None):
        raise HTTPException(status_code=400, detail="User already has premium")

    # 3️⃣ Define premium period & price
    if data.premium_type == "prelaunch":
        price = 149
        duration_days = 30
    else:
        price = 449
        duration_days = 30

    start_date = datetime.utcnow().isoformat()
    end_date = (datetime.utcnow() + timedelta(days=duration_days)).isoformat()

    # 4️⃣ Insert into premium_users safely
    insert_res = supabase.table("premium_users").insert({
        "user_id": data.user_id,
        "name": user.get("name"),
        "email": user.get("email"),
        "premium_type": data.premium_type,
        "start_date": start_date,
        "end_date": end_date,
        "price": price,
        "badge": "soulmate"
    }).execute()

    return {
        "message": "Premium activated successfully 🌟",
        "premium": getattr(insert_res, "data", None)
    }
