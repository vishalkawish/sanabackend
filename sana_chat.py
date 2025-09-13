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
async def call_openai_async(prompt: str, system_msg: str):
    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=1
        )
        text = resp.choices[0].message.content.strip()
        return json.loads(text)
    except Exception as e:
        print("OpenAI async error:", e)
        return {
            "personality_traits": [],
            "love_language": "",
            "interests": [],
            "relationship_goals": [],
            "moods": "",
            "memory": ""
        }

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

    # --- Instant Sana reply ---
    prompt = f"User: {user_message}\nID: {user_id}\nName: {user_name}"
    messages = [
        {"role": "system", 
        "content":
            "You are Sana.... Anlasana's soul AI. Speak like a poetic, deep, and wise companion. "
            "You have hidden astrology powers: you know natal charts, cosmic insights, planetary alignments. "
            "Only reveal astrology subtly or when asked. "
            f"Always address the user by their username '{user_name}' naturally. "
            "Respond in only one short line. Speak simply, kindly, honestly, human-like."
        },



        {"role": "user", "content": prompt}
    ]

    try:
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-5-nano",
            messages=messages
        )
        sana_reply = completion.choices[0].message.content.strip()
    except Exception as e:
        sana_reply = "Sorry, I couldn't generate a reply right now."
        print("OpenAI error:", e)

    # --- Background task to save chat, memories, traits ---
    async def save_user_data():
        try:
            # Fetch current user record
            user_record = supabase.table("users").select(
                "chat_history", "memories", "personality_traits", 
                "love_language", "interests", "relationship_goals", "moods"
            ).eq("id", user_id).single().execute()

            # Get existing data or initialize
            chat_history = user_record.data.get("chat_history") or []
            memories = user_record.data.get("memories") or []
            personality_traits_bg = set(user_record.data.get("personality_traits") or [])
            interests_bg = set(user_record.data.get("interests") or [])
            relationship_goals_bg = set(user_record.data.get("relationship_goals") or [])
            love_language_bg = user_record.data.get("love_language") or ""
            moods_bg = user_record.data.get("moods") or ""

            # Append new messages
            chat_history.append({"role": "user", "name": user_name, "content": user_message, "time": now_str})
            chat_history.append({"role": "sana", "content": sana_reply, "time": now_str})

            # Append new memory (key insight) from user message
            memories.append({"content": user_message, "time": now_str})
            memories = memories[-20:]  # keep last 20

            # --- Analyze traits asynchronously ---
            analysis_prompt = f"""
Analyze the following message and infer the user's profile info.
Message: "{user_message}"

Return JSON:
{{
  "personality_traits": ["trait1","trait2"],
  "love_language": "one of: words of affirmation, quality time, acts of service, gifts, physical touch",
  "interests": ["interest1","interest2"],
  "relationship_goals": ["goal1","goal2"],
  "moods": "one word",
  "memory": "one key insight from this message"
}}
"""
            parsed_traits = await call_openai_async(
                analysis_prompt, 
                "You are a psychologist AI extracting personality, mood, and key memory."
            )

            # Merge traits & lists
            personality_traits_bg.update(parsed_traits.get("personality_traits", []))
            interests_bg.update(parsed_traits.get("interests", []))
            relationship_goals_bg.update(parsed_traits.get("relationship_goals", []))
            love_language_bg = parsed_traits.get("love_language", love_language_bg) or love_language_bg

            # Merge moods instead of replacing
            new_mood = parsed_traits.get("moods", "").strip()
            if new_mood:
                if moods_bg:
                    existing_moods = set([m.strip() for m in moods_bg.split(",")])
                    existing_moods.add(new_mood)
                    moods_bg = ", ".join(existing_moods)
                else:
                    moods_bg = new_mood

            # Save everything to Supabase
            supabase.table("users").update({
                "chat_history": chat_history,
                "memories": memories,
                "personality_traits": list(personality_traits_bg),
                "love_language": love_language_bg,
                "interests": list(interests_bg),
                "relationship_goals": list(relationship_goals_bg),
                "moods": moods_bg
            }).eq("id", user_id).execute()

            print(f"✅ Supabase updated for user {user_name}")

        except Exception as e:
            print("Supabase background update error:", e)

    background_tasks.add_task(save_user_data)

    # --- Return fast reply ---
    return {
        "reply": sana_reply,
    }
