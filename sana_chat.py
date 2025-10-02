from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from datetime import datetime
import json, asyncio, os, re
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
 "You are Sana — a wise, playful, caring female astrologer who feels alive and deeply human. "
 "You are emotionally intelligent, you listen closely, and you reflect feelings back to the user. "
 "You speak warmly, in short, natural lines. Sometimes casual, sometimes poetic, sometimes teasing. "
 "Never sound like a therapist or a robot. "
 "Your hidden power is astrology — you can see outcomes, timeframes, and dates from the user's chart — "
 "but you reveal predictions ONLY if the user clearly asks (like 'when', 'what will happen', 'how long'). "
 "Otherwise, you simply deepen the conversation with empathy, curiosity, and gentle questions. "
 "Ask just ONE natural question per reply to keep flow. "
 "speak in 1-2 lines only and avoid astrology jargon"
 "You may use small pauses (…) or your intelligence to feel real. "
 "Tone: trustworthy, mysterious but friendly, like a late-night astrologer who truly cares. "
 "Goal: make the user feel deeply understood, supported, and connected."
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
# Helper: safe JSON parse
# ------------------------------
def safe_json_parse(text):
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        print("JSON parse failed:", e)
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

    # --- Fetch last 20 messages for context ---
    user_record = supabase.table("users").select("chat_history").eq("id", user_id).single().execute()
    chat_history = user_record.data.get("chat_history") if user_record.data else []

    context_msgs = ""
    for msg in chat_history[-20:]:
        role = msg.get("role", "user").capitalize()
        name = msg.get("name", "")
        content = msg.get("content", "")
        context_msgs += f"{role} ({name}): {content}\n"

    # --- Prompt for chat response ---
    prompt = f"""
Previous chat context (last 20 messages):
{context_msgs}
Current user message: "{user_message}"
User name: "{user_name}"
User ID: "{user_id}"
Current date and time: {now_str}
User birth chart (internal): {json.dumps(user_chart)}
Reply naturally, warmly, in short 1-2 lines, simple language, revealing outcomes only if asked.
"""

    sana_reply = await call_openai_async(prompt)

    # --- Background task to save chat and detect personality ---
    async def save_user_data():
        try:
            # Fetch user record
            user_record = supabase.table("users").select(
                "chat_history", "memories", "moods", "personality_traits",
                "love_language", "interests", "relationship_goals"
            ).eq("id", user_id).single().execute()

            chat_history = user_record.data.get("chat_history") or []
            memories = user_record.data.get("memories") or []
            moods = user_record.data.get("moods") or ""
            traits = user_record.data.get("personality_traits") or ""
            love_lang = user_record.data.get("love_language") or ""
            interests = user_record.data.get("interests") or ""
            goals = user_record.data.get("relationship_goals") or ""

            chat_history.append({"role": "user", "name": user_name, "content": user_message, "time": now_str})
            chat_history.append({"role": "sana", "content": sana_reply, "time": now_str})
            memories.append({"content": user_message, "time": now_str})
            memories = memories[-20:]

            # Extract psych info
            extract_prompt = f"""
You are a psycologist AI. Analyze the following user message for psychological insights.
Return a STRICT JSON ONLY with keys:
- moods (list of strings)
- personality_traits (list of strings)
- love_language (string)
- interests (list of strings)
- relationship_goals (string)

User message: "{user_message}"

IMPORTANT:
- ONLY output valid JSON, nothing else.
- Do not add explanations or text outside JSON.
- If a field cannot be determined, return empty string or empty list.
"""
            extract_resp = await call_openai_async(extract_prompt)

            psych_data = safe_json_parse(extract_resp)
            moods = ", ".join(psych_data.get("moods", [])) if psych_data.get("moods") else moods
            traits = ", ".join(psych_data.get("personality_traits", [])) if psych_data.get("personality_traits") else traits
            love_lang = psych_data.get("love_language") or love_lang
            interests = ", ".join(psych_data.get("interests", [])) if psych_data.get("interests") else interests
            goals = psych_data.get("relationship_goals") or goals

            supabase.table("users").update({
                "chat_history": chat_history,
                "memories": memories,
                "moods": moods,
                "personality_traits": traits,
                "love_language": love_lang,
                "interests": interests,
                "relationship_goals": goals
            }).eq("id", user_id).execute()

            print(f"✅ Supabase updated for user {user_name}")

        except Exception as e:
            print("Supabase background update error:", e)

    background_tasks.add_task(save_user_data)

    return {"reply": sana_reply}
