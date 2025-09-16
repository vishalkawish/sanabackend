# 1️⃣ Load env first
from dotenv import load_dotenv
load_dotenv()

# 2️⃣ Standard imports
import os
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, APIRouter, BackgroundTasks
from pydantic import BaseModel, validator
import requests
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
from demo_matches import router as random_match_router
from premium import premium_activate
from routes import profile_image
from routes import save_phone_number

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
def fetch_user_from_supabase_by_id(user_id: str):
    url = f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}&select=*"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
        return None
    except Exception as e:
        print(f"Error fetching user from Supabase by ID: {e}")
        return None

# ---------------------------
# Full Chart Endpoint
# ---------------------------
router = APIRouter()

# ---------------------------
# Full Chart Endpoint
# ---------------------------
from fastapi import HTTPException



@router.post("/astro/full")
async def get_full_chart(data: NatalData):
    chart_file = USER_CHART_DIR / f"{data.id}.json"

    # --- 1. Fetch user from Supabase ---
    try:
        resp = supabase.table("users").select("*").eq("id", data.id).single().execute()
        user = resp.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase fetch error: {e}")

    if not user:
        raise HTTPException(status_code=404, detail=f"User {data.id} not found")

    # --- 2. Ensure birth info exists ---
    birth = user.get("birth")
    if not birth:
        bd, bt, bp = user.get("birthdate"), user.get("birthtime"), user.get("birthplace")
        if bd and bt and bp:
            try:
                from datetime import datetime
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
                print(f"✅ Migrated birth data for {user['name']}")
            except Exception as e:
                print(f"⚠️ Birth migration failed for {user.get('name')}: {e}")
        else:
            # fallback birth: use default or approximate
            birth = {
                "year": 2000,
                "month": 1,
                "day": 1,
                "hour": 12,
                "minute": 0,
                "place": "Unknown"
            }
            print(f"⚠️ Using fallback birth data for {user['name']}")

    # --- 3. Generate chart if missing ---
    if not chart_file.exists():
        try:
            await generate_chart_for_user(user["id"], birth=birth)
        except Exception as e:
            print(f"⚠️ Chart generation failed, using fallback: {e}")
            # fallback to calculate_chart if generate_chart_for_user fails
            astro_data = await calculate_chart(NatalData(**birth, id=data.id, name=data.name))
            with open(chart_file, "w") as f:
                json.dump(astro_data, f, indent=2)
    # --- 4. Load chart ---
    if chart_file.exists():
        with open(chart_file, "r") as f:
            astro_data = json.load(f)
    else:
        # fallback again if file missing
        astro_data = await calculate_chart(NatalData(**birth, id=data.id, name=data.name))
        with open(chart_file, "w") as f:
            json.dump(astro_data, f, indent=2)

    # --- 5. Build Sana prompt ---
    natal_prompt = f"""
You are Sana, goddess of astrology.
Generate 5 daily insights for {data.name}.
Also add one task for self-discovery and higher dimension.
Tell user about their personality, patterns, secrets and so on using this chart.
Avoid astrology jargon. Only one line each. Address naturally, human-like and in everyday words. User must feel you are real.
Each reflection must have: "title" + "content".
Return ONLY JSON: {{"mirror":[{{"title":"...","content":"..."}}]}}

Chart data: {json.dumps(astro_data, indent=2)}
"""

    # --- 6. Call OpenAI ---
    [natal] = await asyncio.gather(
        call_openai_async(natal_prompt, "You are Sana, a goddess, output JSON only."),
    )

    # --- 7. Return single response ---
   return natal[0]["mirror"]




# ---------------------------
# Personal insights
# ---------------------------
@router.post("/astro/personal") 
async def get_personal_insights(data: NatalData):
    chart_file = USER_CHART_DIR / f"{data.id}.json"
    if not chart_file.exists():
        user = fetch_user_from_supabase_by_id(data.id)
        if user:
            generate_chart_for_user(user["id"])
        else:
            print(f"⚠️ User ID {data.id} not found. Using provided data.")

    astro_data = await calculate_chart(data)
    if not chart_file.exists():
        with open(chart_file, "w") as f:
            json.dump(astro_data, f, indent=2)

    prompt = f"""
You are Sana, goddess of astrology.
Generate personal insights for {data.name} in the following sections:
- third_eye
- you
- higher_dimension
- secret_message_for_you
- awakening
- message_from_universe
Each section must have "title" and "content", one line each. Avoid astrology jargon.
Return ONLY JSON: {{"personal":[{{"title":"...","content":"..."}}]}}
Chart data: {json.dumps(astro_data, indent=2)}
"""
    response = await call_openai_async(prompt, "You are Sana, a goddess, output JSON only.")
    return response

# ---------------------------
# Include routers
# ---------------------------
app.include_router(router)
app.include_router(user_router)
app.include_router(sana_router)
app.include_router(profile_image.router)
app.include_router(random_match_router)
app.include_router(save_phone_number.router)
app.include_router(premium_activate.router, prefix="/api/premium")
app.include_router(soul_router, prefix="/api")

print("Registered routes:")
for r in app.routes:
    print(r.path)
