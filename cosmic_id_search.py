from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx, os

router = APIRouter()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

class CosmicIDRequest(BaseModel):
    cosmic_id: str

@router.post("/fetch_user_by_cosmic_id")
async def fetch_user_summary(request: CosmicIDRequest):
    url = f"{SUPABASE_URL}/rest/v1/users?cosmic_id=eq.{request.cosmic_id}&select=*"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200 and resp.json():
                user = resp.json()[0]
                # Keep only required fields
                summary = {
                    "name": user.get("name"),
                    "cosmic_id": user.get("cosmic_id"),
                    "birthdate": user.get("birthdate"),
                    "birthplace": user.get("birthplace"),
                    "gender": user.get("gender"),
                    "personality_traits": user.get("personality_traits"),
                    "love_language": user.get("love_language"),
                    "interests": user.get("interests"),
                    "profile_url": user.get("profile_pic_url"),
                    "age": user.get("age")
                }
                return {"user": summary}
            else:
                raise HTTPException(status_code=404, detail=f"No user found with Cosmic ID {request.cosmic_id}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase fetch error: {e}")
