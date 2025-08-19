from fastapi import FastAPI
from pydantic import BaseModel
import swisseph as swe
import datetime
from geopy.geocoders import Nominatim
from openai import OpenAI
from dotenv import load_dotenv
import os

# ---------------------------
# Load env
# ---------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY not found in .env file")

# ---------------------------
# Init
# ---------------------------
app = FastAPI()
geolocator = Nominatim(user_agent="anlasana")
client = OpenAI(api_key=OPENAI_API_KEY)

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
    place: str   # Example: "Delhi"

# ---------------------------
# Routes
# ---------------------------
@app.get("/")
def home():
    return {"message": "✨ Anlasana backend is running 🚀"}

@app.post("/astro/natal")
def get_natal_chart(data: NatalData):
    # 1. Convert place → lat/lon
    location = geolocator.geocode(data.place)
    if not location:
        return {"error": f"❌ Place not found: {data.place}"}
    lat, lon = float(location.latitude), float(location.longitude)

    # 2. Convert DOB/TIME → Julian Day
    birth_dt = datetime.datetime(
        data.year, data.month, data.day, data.hour, data.minute
    )
    jd_ut = swe.julday(
        birth_dt.year,
        birth_dt.month,
        birth_dt.day,
        birth_dt.hour + birth_dt.minute / 60.0
    )

    # 3. Calculate houses (Placidus)
    houses, ascmc = swe.houses(jd_ut, lat, lon, b"P")

    # 4. Calculate planet positions
    planets = {}
    planet_names = {
        swe.SUN: "Sun",
        swe.MOON: "Moon",
        swe.MERCURY: "Mercury",
        swe.VENUS: "Venus",
        swe.MARS: "Mars",
        swe.JUPITER: "Jupiter",
        swe.SATURN: "Saturn",
        swe.URANUS: "Uranus",
        swe.NEPTUNE: "Neptune",
        swe.PLUTO: "Pluto"
    }

    for pl, name in planet_names.items():
        xx, ret = swe.calc_ut(jd_ut, pl)
        planets[name] = round(xx[0], 2)  # longitude only

    result = {
        "username": data.username,
        "place": data.place,
        "julian_day": jd_ut,
        "ascendant": round(ascmc[0], 2),
        "midheaven": round(ascmc[1], 2),
        "houses": [round(h, 2) for h in houses],
        "planets": planets
    }

    # ---------------------------
    # AI Interpretation using updated prompt
    # ---------------------------
    prompt = f"""
You are Sana, a warm, human-like emotional mirror and astrology guide.

Use the user's astrology data — planets, houses, aspects, transits, and ephemeris positions — to generate a fully personalized soul reading.

Rules:
1. Generate 10–12 sections, each with a dynamic title and 1–3 sentence content.
2. Titles must never be fixed. They must reflect exactly what the planets, houses, and aspects show.
3. Content must be in plain, simple English, relatable to the user's life, emotions, and current situation.
4. Use astrology to explain feelings, strengths, challenges, desires, and opportunities.
5. Include planetary influences in a natural, human way — no random cosmic terms.
6. Output in JSON only, like this:

{{"sections": [{{"title": "...", "content": "..."}}, ...]}}

No markdown, no poetry, no generic fluff. Make every section specific, warm, and emotional, reflecting the user's unique chart.

User data: {result}
"""

    ai_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are Sana, an emotional mirror and astrology guide."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.8
    )

    reflection = ai_response.choices[0].message.content

    # Return both raw data + dynamic JSON
    return {
        "astro_data": result,
        "reflection": reflection
    }
