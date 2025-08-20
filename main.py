# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, validator
import swisseph as swe
import datetime
import os
import openai
import json
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from dotenv import load_dotenv

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

# ---------------------------
# Routes
# ---------------------------
@app.get("/")
def home():
    return {"message": "✨ Anlasana backend is running 🚀"}

@app.post("/astro/natal")
def get_natal_chart(data: NatalData):
    # ---------------------------
    # Geocode the place
    # ---------------------------
    try:
        location = geolocator.geocode(data.place, timeout=10)
        if not location:
            raise HTTPException(status_code=404, detail=f"Place not found: {data.place}")
        lat, lon = float(location.latitude), float(location.longitude)
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        raise HTTPException(status_code=503, detail=f"Geocoding service unavailable: {e}")

    # ---------------------------
    # Calculate Julian day
    # ---------------------------
    try:
        birth_dt = datetime.datetime(data.year, data.month, data.day, data.hour, data.minute)
        jd_ut = swe.julday(birth_dt.year, birth_dt.month, birth_dt.day, birth_dt.hour + birth_dt.minute / 60)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date/time provided.")

    # ---------------------------
    # Calculate houses and ascendant
    # ---------------------------
    try:
        swe.set_ephe_path(".")
        houses, ascmc = swe.houses(jd_ut, lat, lon, b"P")
    except swe.SweError as e:
        raise HTTPException(status_code=500, detail=f"Swisseph calculation failed: {e}")

    # ---------------------------
    # Calculate planets
    # ---------------------------
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
        try:
            xx, ret = swe.calc_ut(jd_ut, pl)
            planets[name] = round(xx[0], 2)
        except swe.SweError:
            planets[name] = None

    # ---------------------------
    # Build astro data
    # ---------------------------
    astro_data = {
        "username": data.username,
        "place": data.place,
        "julian_day": jd_ut,
        "ascendant": round(ascmc[0], 2),
        "midheaven": round(ascmc[1], 2),
        "houses": [round(h, 2) for h in houses],
        "planets": planets
    }

    # ---------------------------
    # AI Interpretation
    # ---------------------------
    prompt_content = f"""
You are Sana, a master astrologer and emotional mirror. Tell about {data.username} — their feelings, personality, strengths, challenges, desires, patterns, love, career, finnace, and current life situation...
using directly from the user's natal chart and current life to reveal {data.username} secret desires, patterns, weakess. strength, why you feel *** etc..
User's Name: {data.username}
Natal Chart Data:
{json.dumps(astro_data, indent=2)}
Generate 10 dynamic daily life reflections. Each reflection must have:
- a short, clear title, highly engaging
- 1 sentences which is easy-to-understand and trigger human emotions and often use user name {data.username}...
Use simple, warm, everyday English — like Sana is whispering truths to the user like a friend..in very easy words.short words high impact.
Output ONLY valid JSON, like this:
{{"insights":[
  {{"title":"...","content":"..."}}
]}}
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are Sana, soulful astrology AI, output pure JSON only."},
                {"role": "user", "content": prompt_content}
            ],
            temperature=0.5
        )
        reflection_text = response.choices[0].message['content'].strip()
        # Remove any ```json or ``` if OpenAI wraps the output
        reflection_text = reflection_text.replace("```json", "").replace("```", "").strip()
        reflection = json.loads(reflection_text)

    except (json.JSONDecodeError, KeyError, openai.OpenAIError) as e:
        reflection = {"error": "AI did not return valid JSON or OpenAI error", "raw": str(e)}

    return {"astro_data": astro_data, "reflection": reflection}
