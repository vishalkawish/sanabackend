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
# Helpers: Zodiac conversion
# ---------------------------
SIGNS = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"
]

def deg_to_sign(deg: float):
    """Return ('Sign', degree_in_sign) for a 0..360 longitude."""
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
# Core Calculation (shared)
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
            xx, ret = swe.calc_ut(jd_ut, pl)
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
    return astro_data

# ---------------------------
# Natal Endpoint
# ---------------------------
@app.post("/astro/natal")
def get_natal_chart(data: NatalData):
    astro_data = calculate_chart(data)

    prompt_content = f"""
You are Sana, a master astrologer and emotional mirror.
Generate 10 dynamic daily life reflections for {data.username}.
Each item: "title" (short, emotional) + "content" (1 sentence, warm, simple).
Output ONLY JSON: {{"insights":[{{"title":"...","content":"..."}}]}}
Natal Chart Data:
{json.dumps(astro_data, indent=2)}
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
        reflection_text = response.choices[0].message["content"].strip().replace("```json","").replace("```","").strip()
        reflection = json.loads(reflection_text)
    except Exception as e:
        reflection = {"error": f"Natal JSON parse error: {str(e)}"}

    return {"astro_data": astro_data, "natal": reflection}

# ---------------------------
# Soulmate Endpoint
# ---------------------------
@app.post("/astro/soulmate")
def get_soulmate_chart(data: NatalData):
    astro_data = calculate_chart(data)

    prompt_content = f"""
You are Sana, the soulful astrologer of love and destiny.
Generate 7 dynamic soulmate reflections for {data.username}.
Focus on love energy, cosmic match, partner style, cravings, rituals, challenges, healing.
Each item: "title" + "content" (1 sentence, simple, poetic).
Output ONLY JSON: {{"soulmate":[{{"title":"...","content":"..."}}]}}
Natal Chart Data:
{json.dumps(astro_data, indent=2)}
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are Sana, soulful love astrologer, output pure JSON only."},
                {"role": "user", "content": prompt_content}
            ],
            temperature=0.6
        )
        soulmate_text = response.choices[0].message["content"].strip().replace("```json","").replace("```","").strip()
        soulmate = json.loads(soulmate_text)
    except Exception as e:
        soulmate = {"error": f"Soulmate JSON parse error: {str(e)}"}

    return {"astro_data": astro_data, "soulmate": soulmate}

# ---------------------------
# Full Endpoint (Natal + Soulmate + Poetic)
# ---------------------------
@app.post("/astro/full")
def get_full_chart(data: NatalData):
    astro_data = calculate_chart(data)

    natal_prompt = f"""
You are Sana, a master astrologer and a mirror of user soul.
Generate 5 dynamic daily life reflections for {data.username}.
Each item: "title" (short, emotional) + "content" (1 sentence, warm, simple).
tell user why they are like, how they feel, their strength, fear etc using chart below..let user know someone is understanding and reading their soul
Output ONLY JSON: {{"mirror":[{{"title":"...","content":"..."}}]}}
Natal Chart Data:
{json.dumps(astro_data, indent=2)}
"""
    soulmate_prompt = f"""
You are Sana, the master astrologer of love and destiny.
Generate 5 dynamic love reflections for {data.username}.
Focus on love energy, cosmic match, partner style,  {data.username} cravings, rituals for love and grounding, challenges in love, cosmic timing, lucky color and lucky number from charts no guessing.
Each item: "title" + "content".
Output ONLY JSON: {{"love":[{{"title":"...","content":"..."}}]}}
Natal Chart Data:
{json.dumps(astro_data, indent=2)}
"""
    poetic_prompt = f"""
You are Sana, a poetic astrologer. Transform the technical chart into a very very short, soulful reading.
Return ONLY JSON in this shape:
{{
  "poetic": {{
    "opening": "...", 
    "highlights": [
      {{"title":"...","content":"..."}},
      {{"title":"...","content":"..."}},
      {{"color":"...","content":"..."}},
      {{"number":"...","content":"..."}},
      {{"title":"...","content":"..."}}
    ],
    "closing": "..."
  }}
}}
Use the chart below as base.
Natal Chart Data:
{json.dumps(astro_data, indent=2)}
"""

    natal, soulmate, poetic = {}, {}, {}

    try:
        natal_resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"system","content":"You are Sana, soulful astrology AI, output pure JSON only."},
                      {"role":"user","content":natal_prompt}],
            temperature=0.5
        )
        nt = natal_resp.choices[0].message["content"].strip().replace("```json","").replace("```","").strip()
        natal = json.loads(nt)
    except Exception as e:
        natal = {"error": f"Natal JSON parse error: {str(e)}"}

    try:
        sm_resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"system","content":"You are Sana, soulful love astrologer, output pure JSON only."},
                      {"role":"user","content":soulmate_prompt}],
            temperature=0.6
        )
        sm = sm_resp.choices[0].message["content"].strip().replace("```json","").replace("```","").strip()
        soulmate = json.loads(sm)
    except Exception as e:
        soulmate = {"error": f"Soulmate JSON parse error: {str(e)}"}

    try:
        po_resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"system","content":"You are Sana, poetic astrologer, output pure JSON only."},
                      {"role":"user","content":poetic_prompt}],
            temperature=0.7
        )
        po = po_resp.choices[0].message["content"].strip().replace("```json","").replace("```","").strip()
        poetic = json.loads(po)
    except Exception as e:
        poetic = {"error": f"Poetic JSON parse error: {str(e)}"}

    return {
        "natal": natal,
        "soulmate": soulmate,
        "poetic": poetic
    }
