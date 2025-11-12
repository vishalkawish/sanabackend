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


# --- Request Model ---
class SanaGreetingRequest(BaseModel):
    userId: str
    time: str  # "morning", "afternoon", "evening", or "night"


# --- Async OpenAI Call ---
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


# --- Fetch user name from Supabase ---
def fetch_user_name(user_id: str):
    try:
        res = (
            supabase.table("users")
            .select("name")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            full_name = res.data[0].get("name", "there")
            # Extract only the first name
            first_name = full_name.split()[0] if full_name else "there"
            return first_name
        return "there"
    except Exception as e:
        print("⚠️ User name fetch failed:", e)
        return "there"



# --- Fetch recent chat (optional) ---
def fetch_recent_chat_json(user_id: str, limit: int = 10):
    try:
        res = (
            supabase.table("chat_history")
            .select("content, role, time")
            .eq("user_id", user_id)
            .order("time", desc=True)
            .limit(limit)
            .execute()
        )
        if not res.data:
            return []
        return list(reversed(res.data))  # oldest first
    except Exception as e:
        print("⚠️ Chat fetch failed:", e)
        return []


# --- Main Route ---
@router.post("/sana/greeting")
async def sana_dynamic_greeting(data: SanaGreetingRequest):
    name = fetch_user_name(data.userId)
    time_period = data.time.lower()
    chat_history = fetch_recent_chat_json(data.userId)

    formatted_history = "\n".join(
        [f"{m['role']}: {m['content']}" for m in chat_history]
    ) if chat_history else "No chat history."

    prompt = f"""
Time of day: {time_period}
User name: {name}

Recent conversation:
{formatted_history}

You are Sana — an emotional AI who remembers past chats and greets users warmly.
Greet the user according to time of day ("{time_period}") and optionally reference their past emotion.
Be gentle, poetic, and short — one line only.
Example tones:
🌅 Good morning Kawish — your calm feels softer today.
🌞 Good afternoon Kawish — how’s your energy today?
🌙 Good night Kawish — may your mind rest easy tonight.
💫 Hi Kawish — your light feels steady, let's begin again.

Now greet the user:
"""

    greeting = await call_openai_async(prompt, "You are Sana, a poetic emotional AI.")
    return {"greeting": greeting, "time_period": time_period}
