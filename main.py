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



from fastapi import APIRouter, HTTPException
from pathlib import Path
import json, asyncio
from datetime import datetime

router = APIRouter()
USER_CHART_DIR = Path("user_charts")

# make sure this folder exists
from fastapi import HTTPException
from datetime import datetime, date
import asyncio, json, os

@router.post("/astro/full")
async def get_full_chart(data: NatalData):
    chart_file = USER_CHART_DIR / f"{data.id}.json"

    # --- 1. Fetch user from Supabase safely ---
    try:
        resp = supabase.table("users").select("*").eq("id", data.id).single().execute()
        user = resp.data if resp and resp.data else None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase fetch error: {e}")

    if not user:
        raise HTTPException(status_code=404, detail=f"User {data.id} not found")

    # --- 2. Migrate birth if missing ---
    if not user.get("birth"):
        bd, bt, bp = user.get("birthdate"), user.get("birthtime"), user.get("birthplace")
        if bd and bt and bp:
            try:
                dt = datetime.fromisoformat(bd)  # expects YYYY-MM-DD
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
                print(f"✅ Migrated birth data for {user['name']}")
            except Exception as e:
                print(f"⚠️ Birth migration failed for {user.get('name')}: {e}")
        else:
            raise HTTPException(status_code=400, detail=f"Insufficient birth info for {user.get('name')}")

    # --- 3. Calculate age ---
    def calculate_age(year, month, day):
        try:
            today = date.today()
            return today.year - year - ((today.month, today.day) < (month, day))
        except Exception as e:
            print(f"[WARN] Failed age calc: {e}")
            return None

    birth = user["birth"]
    age = calculate_age(birth["year"], birth["month"], birth["day"])
    if age and user.get("age") != age:  # update only if new or changed
        supabase.table("users").update({"age": age}).eq("id", user["id"]).execute()
        user["age"] = age
        print(f"🎂 Age calculated for {user['name']} => {age}")

    # --- 4. Prepare NatalData ---
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

    # --- 5. Generate or load cached chart ---
    if chart_file.exists():
        try:
            with open(chart_file, "r") as f:
                astro_data = json.load(f)
            print(f"📂 Loaded cached chart for {user['name']}")
        except Exception as e:
            print(f"⚠️ Cache load failed: {e}, regenerating...")
            astro_data = await calculate_chart(natal_data)
            with open(chart_file, "w") as f:
                json.dump(astro_data, f)
    else:
        try:
            astro_data = await calculate_chart(natal_data)
            with open(chart_file, "w") as f:
                json.dump(astro_data, f)
            print(f"🪐 Generated and cached chart for {user['name']}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Chart generation failed: {e}")

    # --- 6. Build Sana prompt ---
    natal_prompt = f"""
You are Sana, a wise, playful female, caring astrologer. 
You read the user's birth chart to determine important dates and outcomes.
Do NOT mention astrology, signs, planets, or charts. 
Generate 5 daily insights for {user['name']} (age {age}).
Also add one task for self-discovery and higher dimension.
Each reflection must have: "title" + "content".
Return ONLY JSON: {{"mirror":[{{"title":"...","content":"..."}}]}}
Reply only with a clear, direct outcome, timeframe, or date. One line.
User birth chart (for internal use only): Chart data: {json.dumps(astro_data, indent=2)}
Reply must be accurate.."""

    # --- 7. Call OpenAI (with JSON safety) ---
    try:
        [natal_response] = await asyncio.gather(
            call_openai_async(natal_prompt, "You are Sana, a goddess, output JSON only."),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sana reflection failed: {e}")

    # --- 8. Wrap into Unity-compatible object ---
    sana_mirror_json = {
        "natal": [
            {
                "mirror": natal_response.get("mirror", []),
            }
        ]
    }

    return sana_mirror_json










# ---------------------------
# Personal insights
# ---------------------------
@router.post("/astro/personal") 
async def get_personal_insights(data: NatalData):
    chart_file = USER_CHART_DIR / f"{data.id}.json"
    if not chart_file.exists():
        user = fetch_user_from_supabase_by_id(data.id)
        if user:
           await generate_chart_for_user(user)
        else:
            print(f"⚠️ User ID {data.id} not found. Using provided data.")

    astro_data = await calculate_chart(data)
    if not chart_file.exists():
        with open(chart_file, "w") as f:
            json.dump(astro_data, f, indent=2)

    prompt = f"""
You are Sana, astrology expert.
Generate 3 hidden love secrets of {data.name} in the following sections using chart below:
Each section must have "title" and "content", one line each. "title" must be one word or max two.
use {data.name} or you to address the user naturally.
Avoid astrology jargon.
Return ONLY JSON: {{"personal":[{{"title":"...","content":"..."}}]}}
Chart data: {json.dumps(astro_data, indent=2)}
"""
    response = await call_openai_async(prompt, "You are Sana, a goddess, output JSON only.")
    return response




@router.post("/astro/personaldesire") 
async def get_personal_insights(data: NatalData):
    chart_file = USER_CHART_DIR / f"{data.id}.json"
    if not chart_file.exists():
        user = fetch_user_from_supabase_by_id(data.id)
        if user:
           await generate_chart_for_user(user)
        else:
            print(f"⚠️ User ID {data.id} not found. Using provided data.")

    astro_data = await calculate_chart(data)
    if not chart_file.exists():
        with open(chart_file, "w") as f:
            json.dump(astro_data, f, indent=2)

    prompt = f"""
You are Sana, astrology expert.
Generate 3 hidden love desire of user {data.name} in the following sections using chart below:
Each section must have "title" and "content", one line each. "title" must be one word or max two.
use {data.name} or you to address the user naturally.
Avoid astrology jargon.
Return ONLY JSON: {{"desire":[{{"title":"...","content":"..."}}]}}
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
app.include_router(soul_router)

print("Registered routes:")
for r in app.routes:
    print(r.path)
