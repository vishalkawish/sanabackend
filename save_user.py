from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client
from datetime import datetime, date
import os, json

router = APIRouter()

# 🔑 environment setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# 🧠 model for user data
class UserData(BaseModel):
    id: str
    name: str | None = None
    email: str | None = None
    birthdate: str | None = None
    birthtime: str | None = None
    birthplace: str | None = None
    profilePicUrl: str | None = None
    gender: str | None = None



def calculate_age_from_birthdate(birthdate: str) -> int | None:
    try:
        bd = datetime.fromisoformat(birthdate)
        today = date.today()
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except Exception:
        return None


@router.post("/save_user")
async def save_user(user: UserData):
    """
    Saves or updates a user in Supabase.
    Also auto-calculates age and assigns cosmic_id if missing.
    """
    try:
        # 🟣 Check if user exists
        existing = supabase.table("users").select("*").eq("id", user.id).execute()
        exists = bool(existing.data)
        existing_user = existing.data[0] if exists else None

        user_data = {k: v for k, v in user.model_dump().items() if v is not None}

        # 🧮 Calculate and include age if birthdate is present

        # 🌟 Assign Cosmic ID (only if new user or missing cosmic_id)
        if not exists or not existing_user.get("sana_id"):
            try:
                counter = (
                    supabase.table("settings")
                    .select("value")
                    .eq("key", "max_sana_id")
                    .single()
                    .execute()
                )
                max_id = int(counter.data["value"]) if counter.data else 0
                next_number = max_id + 1
                cosmic_id = f"S{next_number}"

                # update the counter in DB
                supabase.table("settings").update({"value": next_number}).eq("key", "max_sana_id").execute()
                user_data["sana_id"] = cosmic_id
                print(f"🌌 Assigned Cosmic ID {cosmic_id} to {user.name or user.id}")
            except Exception as e:
                print(f"⚠️ Cosmic ID assignment failed: {e}")

        # 🔄 Create or Update user
        if exists:
            result = supabase.table("users").update(user_data).eq("id", user.id).execute()
            print(f"🌀 Updated user {user.id}")
            status = "updated"
        else:
            result = supabase.table("users").insert(user_data).execute()
            print(f"🌟 Created new user {user.id}")
            status = "created"

        # Return the fresh user record
        updated_user = (
            supabase.table("users").select("*").eq("id", user.id).single().execute().data
        )

        return {"status": status, "data": updated_user}

    except Exception as e:
        print("❌ Error saving user:", e)
        raise HTTPException(status_code=500, detail=f"Supabase error: {e}")
