# main.py
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel, validator
import swisseph as swe
import datetime
import os
import json
import asyncio
import openai
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from dotenv import load_dotenv
from pathlib import Path

# ---------------------------
# Load environment
# ---------------------------
load_dotenv()
openai.api_key = os.environ.get("OPENAI_API_KEY")  # no proxies

if not openai.api_key:
    raise RuntimeError("OpenAI API key not found. Set environment variable OPENAI_API_KEY")

app = FastAPI()
geolocator = Nominatim(user_agent="anlasana-astro-api")

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
# Core chart calculation
# ---------------------------
def calculate_chart(data: NatalData):
    # Geocode
    try:
        location = geolocator.geocode(data.place, timeout=10)
        if not location:
            raise HTTPException(status_code=404, detail=f"Place not found: {data.place}")
        lat, lon = float(location.latitude), float(location.longitude)
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        raise HTTPException(status_code=503, detail=f"Geocoding service unavailable: {e}")

    # Time & Julian day
    try:
        birth_dt = datetime.datetime(data.year, data.month, data.day, data.hour, data.minute)
        jd_ut = swe.julday(birth_dt.year, birth_dt.month, birth_dt.day, birth_dt.hour + birth_dt.minute / 60)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date/time provided.")

    # Houses / angles
    try:
        swe.set_ephe_path(".")
        houses, ascmc = swe.houses(jd_ut, lat, lon, b"P")
    except swe.SweError as e:
        raise HTTPException(status_code=500, detail=f"Swisseph calculation failed: {e}")

    # Planets
    planets = {}
    planet_names = {
        swe.SUN: "Sun", swe.MOON: "Moon", swe.MERCURY: "Mercury",
        swe.VENUS: "Venus", swe.MARS: "Mars", swe.JUPITER: "Jupiter",
        swe.SATURN: "Saturn", swe.URANUS: "Uranus", swe.NEPTUNE: "Neptune",
        swe.PLUTO: "Pluto"
    }
    for pl, name in planet_names.items():
        try:
            xx, _ = swe.calc_ut(jd_ut, pl)
            planets[name] = round(xx[0], 2)
        except swe.SweError:
            planets[name] = None

    # Enrich with zodiac signs
    asc_sign, asc_deg = deg_to_sign(ascmc[0])
    mc_sign, mc_deg   = deg_to_sign(ascmc[1])
    planets_signed = planets_with_signs(planets)

    astro_data = {
        "username": data.username,
        "place": data.place,
        "datetime_utc": birth_dt.isoformat(),
        "julian_day": jd_ut,
        "ascendant": {"longitude": round(ascmc[0], 2), "sign": asc_sign, "deg_in_sign": asc_deg},
        "midheaven": {"longitude": round(ascmc[1], 2), "sign": mc_sign, "deg_in_sign": mc_deg},
        "houses": [round(h, 2) for h in houses],
        "planets": planets_signed
    }
    # Save chart locally for chat
    with open(USER_CHART_DIR / f"{data.username}.json", "w") as f:
        json.dump(astro_data, f, indent=2)
    return astro_data

# ---------------------------
# Compatibility score
# ---------------------------
def calculate_compatibility_score(user_chart, crush_chart):
    score = 50
    pairs = [
        ("Sun", "Moon"),
        ("Moon", "Moon"),
        ("Venus", "Mars"),
        ("Mars", "Venus"),
        ("Sun", "Venus"),
        ("Moon", "Venus")
    ]
    for u, c in pairs:
        user_planet = user_chart["planets"].get(u)
        crush_planet = crush_chart["planets"].get(c)
        if not user_planet or not crush_planet:
            continue
        diff = abs(user_planet["longitude"] - crush_planet["longitude"]) % 360
        if diff > 180:
            diff = 360 - diff
        if diff < 5:
            score += 10
        elif diff < 15:
            score += 6
        elif abs(diff - 60) < 5:
            score += 4
        elif abs(diff - 120) < 5:
            score += 5
        elif abs(diff - 90) < 5:
            score -= 3
        elif abs(diff - 180) < 5:
            score -= 5

    # Rescale raw score (50–100) to premium range (76–98)
    min_raw, max_raw = 50, 100
    min_premium, max_premium = 76, 98
    score = min_premium + (score - min_raw) * (max_premium - min_premium) / (max_raw - min_raw)
    return round(score)

# ---------------------------
# Full chart: natal + poetic + love
# ---------------------------
router = APIRouter()

@router.post("/astro/full")
async def get_full_chart(data: NatalData):
    astro_data = calculate_chart(data)

    natal_prompt = f"""
You are Sana, You're Godess.who know astrology 
Generate 5 short, daily insights for {data.username}....
and tell user who is he(personality, pattern etc) using this chart...
{json.dumps(astro_data, indent=2)}
avoid astrology jargon.Only one Line.
Address the user naturally: sometimes call them by their name ({data.username}), sometimes use 'you'. 
Avoid astrology terms (no planets, signs, houses, etc.).
Each reflection must have: "title" + "content".
Return ONLY JSON exactly like this:
{{"mirror":[{{"title":"...","content":"..."}}]}}

"""

    poetic_prompt = f"""
You are Sana, a poetic guide. Write a short soulful message for {data.username}. 
Address the user naturally: sometimes use 'you', sometimes their name ({data.username}). 
Keep it simple and inspiring, no astrology jargon.
Return ONLY JSON in this shape:
{{"poetic":{{"opening":"...","highlights":[{{"title":"...","content":"..."}}],"closing":"..."}}}}
Chart data for inspiration:
{json.dumps(astro_data, indent=2)}
"""

    love_prompt = f"""
You are Sana, a gentle love guide. 
Create 5 one-line love reflections for {data.username}, written in clear, everyday language. 
Address the user naturally: sometimes 'you', sometimes their name ({data.username}). 
No astrology jargon.
Each item must have: "title" + "content".
Return ONLY JSON exactly like this:
{{"love":[{{"title":"...","content":"..."}}]}}
Chart data for inspiration:
{json.dumps(astro_data, indent=2)}
"""

    async def call_openai(prompt, system_msg):
        try:
            resp = await openai.ChatCompletion.acreate(
                model="gpt-5-nano",
                messages=[{"role": "system", "content": system_msg},{"role": "user", "content": prompt}],
                temperature=1
            )
            text = resp.choices[0].message["content"].strip()
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            return {"error": str(e)}

    natal, poetic, love = await asyncio.gather(
        call_openai(natal_prompt, "You are Sana, a life guide, output JSON only."),
        call_openai(poetic_prompt, "You are Sana, poetic life guide, output JSON only."),
        call_openai(love_prompt, "You are Sana, love guide, output JSON only."),
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
You are Sana, a gentle love guide.
Write 8 short compatibility reflections between {data.username} and {data.crush_name}.
Use clear, everyday language — no astrology jargon.
Each item must have "title" and "content".
Make it warm, human, and easy to read.
Return ONLY JSON in this exact structure:
{{"compatibility":[{{"title":"...","content":"..."}}]}}
Also include the overall score: {score}
"""

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-5-nano",
            messages=[{"role":"system","content":"You are Sana, a love guide AI. Output JSON only."},
                      {"role":"user","content":match_prompt}],
            temperature=1
        )
        comp_raw = resp.choices[0].message["content"].strip().replace("```json","").replace("```","").strip()
        compatibility = json.loads(comp_raw)
    except Exception as e:
        compatibility = {"error": str(e)}
    return {"score": score, "compatibility": compatibility}

# ---------------------------
# Sana chat endpoint
# ---------------------------
@app.post("/sana/chat")
def sana_chat(data: SanaChatMessage):
    history_file = CHAT_HISTORY_DIR / f"{data.username}.json"
    memory_file = MEMORY_DIR / f"{data.username}.json"
    chart_file = USER_CHART_DIR / f"{data.username}.json"

    conversation = []
    if history_file.exists():
        with open(history_file, "r") as f:
            conversation = json.load(f)

    user_chart = {}
    if chart_file.exists():
        with open(chart_file, "r") as f:
            user_chart = json.load(f)

    memory_summary = ""
    if memory_file.exists():
        with open(memory_file, "r") as f:
            memory_summary = json.load(f).get("summary", "")

    conversation.append({"role": "user", "content": data.message})

    system_prompt = {
        "role": "system",
        "content": (
            "You are Sana.... Anlasana's soul AI. Speak like a poetic, deep, and wise companion. "
            "You have hidden astrology powers: you know natal charts, cosmic insights, planetary alignments. "
            "Only reveal astrology subtly or when asked. "
            f"Always address the user by their username '{data.username}' naturally. "
            "Respond in only one short line. Speak simply, kindly, honestly, human-like."
        )
    }

    chart_context = ""
    if user_chart:
        chart_context = f"\n\nUser's natal chart:\n{json.dumps(user_chart, indent=2)}"

    messages_to_send = [system_prompt]
    if memory_summary:
        messages_to_send.append({"role": "system", "content": f"User memory summary:\n{memory_summary}"})
    messages_to_send += conversation[-15:]
    if chart_context:
        messages_to_send.append({"role": "system", "content": chart_context})

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-5-nano",
            messages=messages_to_send,
            temperature=1
        )
        sana_reply = resp.choices[0].message["content"].strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sana API error: {e}")

    conversation.append({"role": "assistant", "content": sana_reply})

    with open(history_file, "w") as f:
        json.dump(conversation, f, indent=2)

    try:
        summary_resp = openai.ChatCompletion.create(
            model="gpt-5-nano",
            messages=[{"role": "system", "content": "You are Sana. Summarize user's chat and traits in short points."},
                      {"role": "user", "content": json.dumps(conversation[-20:])}],
            temperature=0
        )
        new_summary = summary_resp.choices[0].message["content"].strip()
        with open(memory_file, "w") as f:
            json.dump({"summary": new_summary}, f, indent=2)
    except:
        pass

    return {"reply": sana_reply}

# Register router
app.include_router(router)