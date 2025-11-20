import os, json, asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
router = APIRouter()


class SanaGreetingRequest(BaseModel):
    userId: str


# -------- Fetch User Psychological Profile --------
def fetch_user_profile(user_id: str):
    try:
        res = (
            supabase.table("users")
            .select(
                "name, moods, personality_traits, love_language, interests, relationship_goals"
            )
            .eq("id", user_id)
            .single()
            .execute()
        )
        return res.data
    except Exception as e:
        print("⚠️ Profile fetch failed:", e)
        return None


# -------- OpenAI Async Wrapper --------
async def call_openai_async(prompt: str, system_msg: str):
    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=1,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sana AI error: {e}")


# -------- Main Greeting Route --------
@router.post("/sana/greeting")
async def sana_dynamic_greeting(data: SanaGreetingRequest):
    profile = fetch_user_profile(data.userId)

    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    # Extract name only
    name = profile.get("name", "there").split()[0]

    prompt = f"""
Give one psychological reflection based on:
name: {name}
Moods: {profile.get("moods")}
Personality traits: {profile.get("personality_traits")}
Love language: {profile.get("love_language")}
Interests: {profile.get("interests")}
Relationship goals: {profile.get("relationship_goals")}

Rules:
• One line max...Pick one key insight from the data above
• Simple, human language, their name or a nickname based on their name 
• Make them feel safe, prepared, and understood
• No poetry, no metaphors
Formart : Insight heading(for example Qualties about you, weakness etc)  • reflection
"""

    greeting = await call_openai_async(prompt, "You are Sana, a deeply human AI psychologist.")
    return {"greeting": greeting}
