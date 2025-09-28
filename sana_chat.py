from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from datetime import datetime
import json, asyncio, os
from openai import OpenAI
from supabase import create_client

# ------------------------------
# Environment & Supabase
# ------------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------------------
# Router
# ------------------------------
router = APIRouter()

class SanaChatMessage(BaseModel):
    id: str
    name: str
    message: str  

# ------------------------------
# Helper: call OpenAI async
# ------------------------------
async def call_openai_async(prompt: str):
    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content":
                 "You are Sana, a warm, playful female, caring astrologer. "
                 "You read the user's birth chart to determine important dates and outcomes. "
                 "Do NOT mention astrology, signs, planets, or charts. "
                 "Reply must be accurate. "
                 "Always reply with direct outcomes, dates, or timeframes in one sweet, human-like line."
                 "only reveal outcomes, dates, or timeframes. when asked."
                 },
                {"role": "user", "content": prompt}
            ],
            temperature=1
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI async error:", e)
        return "Sorry, I couldn't generate a reply right now."

# ------------------------------
# Helper: fetch chart from Supabase
# ------------------------------
def fetch_user_chart(user_id: str):
    try:
        resp = supabase.table("users").select("chart").eq("id", user_id).single().execute()
        chart_str = resp.data.get("chart") if resp.data else None
        if not chart_str:
            return {}
        return json.loads(chart_str.replace('\\"', '"'))
    except Exception as e:
        print(f"Error fetching chart: {e}")
        return {}

# ------------------------------
# Chat Endpoint
# ------------------------------
@router.post("/sana/chat")
async def sana_chat(data: SanaChatMessage, background_tasks: BackgroundTasks):
    user_id = data.id
    user_name = data.name
    user_message = data.message

    if not all([user_id, user_name, user_message]):
        raise HTTPException(status_code=400, detail="Missing id, name, or message")

    now_str = str(datetime.now())
    user_chart = fetch_user_chart(user_id)

    # Prompt includes chart internally but user never sees astrology
    prompt = f"""
User message: "{user_message}"
User name: "{user_name}"
User ID: "{user_id}"
Current date and time: {now_str}
User birth chart (for internal use only): {json.dumps(user_chart)}
Reply only with a clear, direct outcome, timeframe, or date. One line.
Reply must be accurate and reveal only when asked.
"""

    sana_reply = await call_openai_async(prompt)

    # --- Background task to save chat ---
    async def save_user_data():
        try:
            user_record = supabase.table("users").select(
                "chat_history", "memories"
            ).eq("id", user_id).single().execute()

            chat_history = user_record.data.get("chat_history") or []
            memories = user_record.data.get("memories") or []

            chat_history.append({"role": "user", "name": user_name, "content": user_message, "time": now_str})
            chat_history.append({"role": "sana", "content": sana_reply, "time": now_str})

            memories.append({"content": user_message, "time": now_str})
            memories = memories[-20:]

            supabase.table("users").update({
                "chat_history": chat_history,
                "memories": memories
            }).eq("id", user_id).execute()

            print(f"✅ Supabase updated for user {user_name}")
        except Exception as e:
            print("Supabase background update error:", e)

    background_tasks.add_task(save_user_data)

    return {"reply": sana_reply}
