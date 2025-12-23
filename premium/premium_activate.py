
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
    tier_mapping = {
        "basic": {"price": 299, "days": 30, "badge": "basic"},
        "recommended": {"price": 499, "days": 30, "badge": "recommended"},
        "elite": {"price": 999, "days": 30, "badge": "elite"}
    }

    tier = data.premium_type.lower()
    if tier not in tier_mapping:
        raise HTTPException(status_code=400, detail=f"Invalid premium type. Choose from: {list(tier_mapping.keys())}")

    price = tier_mapping[tier]["price"]
    duration_days = tier_mapping[tier]["days"]
    badge = tier_mapping[tier]["badge"]

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
        "badge": badge
    }).execute()

    return {
        "message": "Premium activated successfully 🌟",
        "premium": getattr(insert_res, "data", None)
    }

# -------------------------
# Check Premium Status endpoint
# -------------------------
@router.get("/status/{user_id}")
def get_premium_status(user_id: str):
    # 1️⃣ Fetch from premium_users
    res = supabase.table("premium_users").select("*").eq("user_id", user_id).maybe_single().execute()
    
    if not res or not getattr(res, "data", None):
        return {
            "is_premium": False,
            "premium_type": "free",
            "badge": "none",
            "days_remaining": 0,
            "end_date": None,
            "message": "No active premium subscription found."
        }
    
    data = res.data
    end_date_str = data.get("end_date")
    
    if not end_date_str:
        return {
            "is_premium": False,
            "premium_type": "free",
            "badge": "none",
            "days_remaining": 0,
            "end_date": None,
            "message": "Invalid subscription data."
        }

    # 2️⃣ Calculate days remaining
    try:
        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        now = datetime.utcnow()
        remaining = (end_date - now).days
        
        is_active = remaining > 0
        
        return {
            "is_premium": is_active,
            "premium_type": data.get("premium_type", "unknown") if is_active else "expired",
            "badge": data.get("badge", "soulmate") if is_active else "none",
            "days_remaining": max(0, remaining),
            "end_date": end_date_str,
            "message": "Active subscription found." if is_active else "Subscription has expired."
        }
    except Exception as e:
        return {
            "is_premium": False,
            "premium_type": "error",
            "badge": "none",
            "days_remaining": 0,
            "end_date": end_date_str,
            "message": f"Error parsing expiry: {str(e)}"
        }
