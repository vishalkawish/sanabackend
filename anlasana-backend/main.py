# main.py
from fastapi import FastAPI
from pydantic import BaseModel
import swisseph as swe
import datetime
from geopy.geocoders import Nominatim
from openai import OpenAI
import os

# ---------------------------
# Init
# ---------------------------
app = FastAPI()
geolocator = Nominatim(user_agent="anlasana")

# OpenAI client reads key automatically from env
client = OpenAI()  # ensure OPENAI_API_KEY is set in Render environment variables

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
    # AI Interpretation yes
    # ---------------------------
    prompt = f"""
    You are Sana, an emotional mirror and master astrologer.
    Use {data.username}'s astrology, planetary positions, houses, aspects, and transits
    to generate a fully personalized, easy-to-understand soul reading.
    Generate 10–12 sections in JSON format:
    {{ "sections": [ {{ "title": "...", "content": "..." }}, ... ] }}
    Tone: human, warm, gentle, and emotional. Each content 1–3 sentences max.
    Important: No markdown, no explanations, output PURE JSON only.
    """

    ai_response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are Sana, a soulful astrology guide."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.8
    )

    reflection = ai_response.choices[0].message.content

    return {
        "astro_data": result,
        "reflection": reflection
    }
