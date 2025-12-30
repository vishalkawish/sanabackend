# 1️⃣ Load env first
from dotenv import load_dotenv
load_dotenv()

# 2️⃣ Standard imports
import os
import aiofiles
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, APIRouter, BackgroundTasks
from pydantic import BaseModel, validator
import requests
import httpx # Adding for async requests if needed, otherwise will use to_thread
from datetime import datetime, date
import swisseph as swe
from openai import OpenAI

# 3️⃣ Supabase import
from supabase import create_client

# 4️⃣ Local imports
from charts import calculate_chart, NatalData
from helpers import generate_chart_for_user
from compatibility import calculate_compatibility_score
from fetchuser import router as user_router
from sana_chat import router as sana_router
from soul_of_anlasana_2_1 import router as soul_router
from sana_psych_worker import router as psych_router
from premium import premium_activate
from save_user import router as save_user_router
from routes import profile_image
from realtime_chat import app as chat_app
from sana_dynamic_greeting import router as sana_dynamic_greeting_router
from update_device_token import router as update_device_token_router

# ---------------------------
# Environment variables
# ---------------------------
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
    id: str
    name: str
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


class SanaChatMessage(BaseModel):
    id: str
    name: str
    message: str  # Removed username; use Supabase name

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
# Home
# ---------------------------
@app.get("/")
def home():
    return {"message": "✨ Anlasana backend is running 🚀"}

# ---------------------------
# OpenAI wrapper (sync -> async)
# ---------------------------
async def call_openai_async(prompt, system_msg):
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
# Supabase fetch
# ---------------------------
async def fetch_user_from_supabase_by_id(user_id: str):
    url = f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}&select=*"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        # Using to_thread to avoid blocking the event loop
        def sync_get():
            return requests.get(url, headers=headers)
        
        resp = await asyncio.to_thread(sync_get)
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
        return None
    except Exception as e:
        print(f"Error fetching user from Supabase by ID: {e}")
        return None

# ---------------------------
# Full Chart Endpoint
# ---------------------------
# ---------------------------
# Full Chart Router
# ---------------------------
router = APIRouter()

def calculate_age_from_birthdate(birthdate: str | None) -> int | None:
    if not birthdate:
        return None

    try:
        # Handle if Supabase sends a dict, null, or extra quotes
        if isinstance(birthdate, dict):
            birthdate = birthdate.get("date")
        if not isinstance(birthdate, str):
            birthdate = str(birthdate)

        birthdate = birthdate.strip().strip('"').strip("'")

        # Try parsing using ISO or common patterns
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                bd = datetime.strptime(birthdate, fmt)
                break
            except ValueError:
                bd = None

        if bd is None:
            # As a last fallback
            bd = datetime.fromisoformat(birthdate)

        today = date.today()
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except Exception as e:
        print(f"⚠️ Age calculation failed for '{birthdate}': {e}")
        return None


@router.post("/astro/full")
async def get_full_chart(data: NatalData):
    # --- 1. Fetch user ---
    try:
        resp = supabase.table("users").select("*").eq("id", data.id).single().execute()
        user = resp.data if resp and resp.data else None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase fetch error: {e}")
    if not user:
        raise HTTPException(status_code=404, detail=f"User {data.id} not found")

    
    birthdate = user.get("birthdate")
    if birthdate:
        age = calculate_age_from_birthdate(birthdate)
        if age is not None:
            user["age"] = age
            try:
               supabase.table("users").update({"age": age}).eq("id", user["id"]).execute()
               print(f"✅ Age updated for {user['id']}: {age}")
            except Exception as e:
               print(f"⚠️ Failed to update age: {e}")

    # --- 2. Ensure birth data exists ---
    birth = user.get("birth")
    if not birth:
        bd, bt, bp = user.get("birthdate"), user.get("birthtime"), user.get("birthplace")
        if bd and bt and bp:
            dt = datetime.fromisoformat(bd)
            hour, minute, *_ = map(int, bt.split(":"))
            birth = {
                "year": dt.year,
                "month": dt.month,
                "day": dt.day,
                "hour": hour,
                "minute": minute,
                "place": bp
            }
            supabase.table("users").update({"birth": birth}).eq("id", user["id"]).execute()
            user["birth"] = birth
        else:
            raise HTTPException(status_code=400, detail=f"Insufficient birth info for {user.get('name')}")

    # now birth is guaranteed to exist
    natal_data = NatalData(
        id=user["id"],
        name=user.get("name", "Unknown"),
        year=birth["year"],
        month=birth["month"],
        day=birth["day"],
        hour=birth.get("hour", 0),
        minute=birth.get("minute", 0),
        place=birth["place"]
    )

    # --- 6. Load or generate chart (Supabase cache, no files) ---
    async def load_or_generate_chart():
        chart_data = user.get("chart")
        if chart_data:
            try:
                if isinstance(chart_data, str):
                    chart_data = json.loads(chart_data.strip('"'))
                return chart_data
            except json.JSONDecodeError:
                pass

        astro_data = await calculate_chart(natal_data)
        try:
            supabase.table("users").update({"chart": json.dumps(astro_data)}).eq("id", user["id"]).execute()
        except Exception as e:
            print(f"⚠️ Failed to save chart for {user['id']}: {e}")
        return astro_data

    astro_data = await load_or_generate_chart()

    # --- 7. Build OpenAI prompt ---
    now_str = str(datetime.now())
    natal_prompt = f"""
Current date: {now_str}
User chart: {json.dumps(astro_data)}
You are Sana, playful female astrologer.
The user's birth place is: {natal_data.place}.
If the birth place is in India, reply in English.
otherwise, reply in the main language of that country.
If unknown, reply in English.
User info: {user.get('chat_history')}, moods: {user.get('moods')}, personality: {user.get('personality_traits')},
love language: {user.get('love_language')}, goals: {user.get('relationship_goals')}, interests: {user.get('interests')}
Avoid astrology jargon and planet names.
Use simple, warm language — 1–2 lines each.
Also, using user info (moods, personality, love language, goals, etc.), generate 5 self-understanding insights.
Each entry must have: "title" and "content".
Return ONLY JSON with structure: {{'mirror':[{{'title':'...','content':'...'}}]}}
"""

    # --- 8. Call OpenAI async ---
    try:
        [natal_response] = await asyncio.gather(call_openai_async(natal_prompt, "You are Sana, JSON only"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sana reflection failed: {e}")

    return {"natal": [{"mirror": natal_response.get("mirror", [])}]}





# ---------------------------
# Include routers
# ---------------------------
app.include_router(router)
app.include_router(user_router)
app.include_router(sana_router)
app.include_router(profile_image.router)
app.include_router(premium_activate.router, prefix="/api/premium")
app.include_router(soul_router)
app.include_router(psych_router)
app.include_router(save_user_router)
app.include_router(sana_dynamic_greeting_router)
app.include_router(update_device_token_router)
app.mount("/", chat_app)

