# 1️⃣ Load env first
from dotenv import load_dotenv
load_dotenv()

# 2️⃣ Standard imports
import os
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel, validator
import requests
import swisseph as swe
from openai import OpenAI

# 3️⃣ Supabase import
from supabase import create_client

# 4️⃣ Local imports
from match import router as match_router, get_best_matches
from charts import calculate_chart, NatalData
from helpers import generate_chart_for_user
from compatibility import calculate_compatibility_score
from fetchuser import router as user_router    # import router directly
from soulmateportal import user_actions 


# 5️⃣ Environment variables
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OpenAI API key not found. Set environment variable OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

# ---------------------------
# Directories
# ---------------------------
USER_CHART_DIR = Path("./user_charts")
USER_CHART_DIR.mkdir(exist_ok=True)
CHAT_HISTORY_DIR = Path("./sana_chat_history")
CHAT_HISTORY_DIR.mkdir(exist_ok=True)
MEMORY_DIR = Path("./sana_chat_memory")
MEMORY_DIR.mkdir(exist_ok=True)

# ---------------------------
# Models
# ---------------------------
class NatalData(BaseModel):
    username: str
    year: int
    month: int
    day: int
    hour: int
    minute: int
    place: str

    @validator("hour")
    def valid_hour(cls, v):
        if not 0 <= v <= 23:
            raise ValueError("Hour must be between 0 and 23")
        return v

    @validator("minute")
    def valid_minute(cls, v):
        if not 0 <= v <= 59:
            raise ValueError("Minute must be between 0 and 59")
        return v

class MatchData(NatalData):
    crush_name: str
    crush_year: int
    crush_month: int
    crush_day: int
    crush_hour: int
    crush_minute: int
    crush_place: str

class SanaChatMessage(BaseModel):
    username: str
    message: str

# ---------------------------
# Zodiac Helpers
# ---------------------------
SIGNS = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"
]

def deg_to_sign(deg: float):
    deg = deg % 360.0
    idx = int(deg // 30)
    sign = SIGNS[idx]
    deg_in_sign = round(deg - idx*30, 2)
    return sign, deg_in_sign

def planets_with_signs(planets_dict):
    out = {}
    for name, lon in planets_dict.items():
        if lon is None:
            out[name] = None
        else:
            s, d = deg_to_sign(lon)
            out[name] = {"longitude": round(lon, 2), "sign": s, "deg_in_sign": d}
    return out

# ---------------------------
# Routes
# ---------------------------
@app.get("/")
def home():
    return {"message": "✨ Anlasana backend is running 🚀"}

# ---------------------------
# OpenAI wrapper (sync -> async)
# ---------------------------
async def call_openai_async(prompt, system_msg):
    """Run OpenAI sync call in async-friendly way."""
    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-5-nano",
            messages=[{"role":"system","content":system_msg},{"role":"user","content":prompt}],
            temperature=1
        )
        text = resp.choices[0].message.content.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}

# ---------------------------
# Fetch Supabase user
# ---------------------------
def fetch_user_from_supabase_by_username(username: str):
    url = f"{SUPABASE_URL}/rest/v1/users?username=eq.{username}&select=*"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
        return None
    except Exception as e:
        print(f"Error fetching user from Supabase: {e}")
        return None

# ---------------------------
# Full chart endpoint
# ---------------------------
router = APIRouter()

@router.post("/astro/full")
async def get_full_chart(data: NatalData):
    chart_file = USER_CHART_DIR / f"{data.username}.json"

    if not chart_file.exists():
        user = fetch_user_from_supabase_by_username(data.username)
        if user:
            generate_chart_for_user(user["id"])
        else:
            print(f"⚠️ User {data.username} not found in Supabase. Using provided data.")

    astro_data = await calculate_chart(data)

    natal_prompt = f"""
You are Sana, You're goddess.who know astrology.
Generate 5 daily insights for {data.username}...
also add one task for self discover and higher dimension.
Tell user about their personality, patterns using this chart.
Avoid astrology jargon. Only one line. Address naturally.
Each reflection must have: "title" + "content".
Return ONLY JSON: {{"mirror":[{{"title":"...","content":"..."}}]}}
Chart data: {json.dumps(astro_data, indent=2)}
"""

    poetic_prompt = f"""
You are Sana, poetic guide. Write a short soulful message for {data.username}.
Address naturally. Keep simple, inspiring. No astrology jargon.
Return ONLY JSON: {{"poetic":{{"opening":"...","highlights":[{{"title":"...","content":"..."}}],"closing":"..."}}}}
Chart data: {json.dumps(astro_data, indent=2)}
"""

    love_prompt = f"""
You are Sana, soulmate of {data.username}. W Write 5 one-line love reflections for {data.username} everyday language.
Each item: "title" + "content". Avoid astrology jargon.
Return ONLY JSON: {{"love":[{{"title":"...","content":"..."}}]}}
Chart data: {json.dumps(astro_data, indent=2)}
"""

    natal, poetic, love = await asyncio.gather(
        call_openai_async(natal_prompt, "You are Sana, a goddess, output JSON only."),
        call_openai_async(poetic_prompt, "You are Sana, poetic life guide, output JSON only."),
        call_openai_async(love_prompt, "You are Sana, love guide, output JSON only."),
    )

    return {"natal": natal, "poetic": poetic, "love": love}

# ---------------------------
# Match compatibility
# ---------------------------
@app.post("/astro/match")
def match_compatibility(data: MatchData):
    user_chart = calculate_chart(data)
    crush_chart = calculate_chart(NatalData(
        username=data.crush_name,
        year=data.crush_year,
        month=data.crush_month,
        day=data.crush_day,
        hour=data.crush_hour,
        minute=data.crush_minute,
        place=data.crush_place
    ))
    score = calculate_compatibility_score(user_chart, crush_chart)

    match_prompt = f"""
You are Sana, love guide. Write 8 short compatibility reflections between {data.username} and {data.crush_name}.
Clear, warm, human language. Each item: "title" + "content". Return ONLY JSON.
Include overall score: {score}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[{"role":"system","content":"You are Sana, love guide AI. Output JSON only."},
                      {"role":"user","content":match_prompt}],
            temperature=1
        )
        comp_raw = resp.choices[0].message.content.strip().replace("```json","").replace("```","").strip()
        compatibility = json.loads(comp_raw)
    except Exception as e:
        compatibility = {"error": str(e)}

    return {"score": score, "compatibility": compatibility}

# ---------------------------
@app.post("/sana/chat")
def sana_chat(data: SanaChatMessage):
    history_file = CHAT_HISTORY_DIR / f"{data.username}.json"
    memory_file = MEMORY_DIR / f"{data.username}.json"
    chart_file = USER_CHART_DIR / f"{data.username}.json"

    # Load conversation history
    conversation = []
    if history_file.exists():
        with open(history_file, "r") as f:
            conversation = json.load(f)

    # Load structured memory
    memory_data = {"summary": "", "name": data.username}
    if memory_file.exists():
        with open(memory_file, "r") as f:
            memory_data.update(json.load(f))

    # Append user message
    conversation.append({"role": "user", "content": data.message})

    # System prompt that *always uses user's name*
    system_prompt = {
        "role": "system",
        "content": (
            f"You are Sana, A goddess of astrology but avoid astrology jargon and Anlasna's soul AI. "
            f"Speak like a poetic, deep, wise companion. "
            f"Always call the user by name: '{memory_data.get('name', data.username)}'. "
            "You remember what they like, their traits, and previous chats. "
            "Respond in one short line only, kindly and honestly."
        )
    }

    # Inject memory + chart context
    messages_to_send = [system_prompt]
    if memory_data.get("summary"):
        messages_to_send.append({
            "role": "system",
            "content": f"User memory summary:\n{memory_data['summary']}"
        })
    if chart_file.exists():
        with open(chart_file, "r") as f:
            user_chart = json.load(f)
            messages_to_send.append({
                "role": "system",
                "content": f"User chart:\n{json.dumps(user_chart, indent=2)}"
            })

    # Add last conversation turns
    messages_to_send += conversation[-15:]

    # Get Sana reply
    try:
        resp = client.chat.completions.create(
            model="gpt-5-nano",
            messages=messages_to_send,
            temperature=1
        )
        sana_reply = resp.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sana API error: {e}")

    # Save conversation history
    conversation.append({"role": "assistant", "content": sana_reply})
    with open(history_file, "w") as f:
        json.dump(conversation, f, indent=2)

    # 🔥 Update memory asynchronously
    def update_memory():
        try:
            summary_resp = client.chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": (
                        "Summarize what the user is like, their preferences, and traits in short points. "
                        "Keep it concise and personal."
                    )},
                    {"role": "user", "content": json.dumps(conversation[-20:])}
                ],
                temperature=1
            )
            new_summary = summary_resp.choices[0].message.content.strip()
            memory_data["summary"] = new_summary
            with open(memory_file, "w") as f:
                json.dump(memory_data, f, indent=2)
        except:
            pass

    import threading
    threading.Thread(target=update_memory, daemon=True).start()

    return {"reply": sana_reply}


# ---------------------------
# Match suggestions
# ---------------------------
@app.get("/astro/find_matches/{user_id}")
def find_matches(user_id: str, top_n: int = 5):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}&select=*", headers=headers)
    if resp.status_code != 200 or not resp.json():
        raise HTTPException(status_code=404, detail="User not found")
    current_user = resp.json()[0]
    username = current_user["name"]

    chart_file = USER_CHART_DIR / f"{username}.json"
    if not chart_file.exists():
        raise HTTPException(status_code=404, detail="User chart not found")

    with open(chart_file, "r") as f:
        user_chart = json.load(f)

    all_users_resp = requests.get(f"{SUPABASE_URL}/rest/v1/users?select=*", headers=headers)
    if all_users_resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch users from Supabase")

    users = all_users_resp.json()
    matches = []
    for u in users:
        if u["id"] == user_id: continue
        chart_path = USER_CHART_DIR / f"{u['name']}.json"
        if not chart_path.exists(): continue
        with open(chart_path, "r") as f:
            crush_chart = json.load(f)
        score = calculate_compatibility_score(user_chart, crush_chart)
        matches.append({"id": u["id"], "username": u["name"], "score": score})

    matches_sorted = sorted(matches, key=lambda x: x["score"], reverse=True)[:top_n]
    return {"matches": matches_sorted}

@app.get("/matches/{user_id}")
def get_matches(user_id: str):
    matches = get_best_matches(user_id)
    if not matches:
        raise HTTPException(status_code=404, detail="No matches found")
    return {"user_id": user_id, "matches": matches}

# ---------------------------
# Include routers
# ---------------------------
app.include_router(match_router)
app.include_router(router)
app.include_router(user_router)
app.include_router(user_actions.router, prefix="/api")

