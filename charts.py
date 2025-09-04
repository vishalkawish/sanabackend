# charts.py
import datetime
import json
from pathlib import Path
from fastapi import HTTPException
import swisseph as swe
import os
from dotenv import load_dotenv
from openai import OpenAI
import asyncio

# -------------------------
# Load environment variables
# -------------------------
load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OpenAI API key not found. Set OPENAI_API_KEY in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

# -------------------------
# Directories and cache
# -------------------------
USER_CHART_DIR = Path("./user_charts")
USER_CHART_DIR.mkdir(exist_ok=True)

GEO_CACHE_FILE = Path("./geo_cache.json")
if not GEO_CACHE_FILE.exists():
    GEO_CACHE_FILE.write_text("{}")

# -------------------------
# Natal data structure
# -------------------------
class NatalData:
    def __init__(self, username, year, month, day, hour, minute, place):
        self.username = username
        self.year = year
        self.month = month
        self.day = day
        self.hour = hour
        self.minute = minute
        self.place = place

# -------------------------
# Utility functions
# -------------------------
def deg_to_sign(deg):
    signs = [
        "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
        "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"
    ]
    sign_index = int(deg // 30)
    deg_in_sign = deg % 30
    return signs[sign_index], round(deg_in_sign, 2)

def planets_with_signs(planets):
    signed = {}
    for name, deg in planets.items():
        if deg is not None:
            sign, deg_in_sign = deg_to_sign(deg)
            signed[name] = {"longitude": deg, "sign": sign, "deg_in_sign": deg_in_sign}
        else:
            signed[name] = {"longitude": None, "sign": None, "deg_in_sign": None}
    return signed

# -------------------------
# Geocoding using OpenAI (async-safe)
# -------------------------
async def geocode_with_openai(place: str):
    cache = json.loads(GEO_CACHE_FILE.read_text())
    if place in cache:
        return cache[place]["lat"], cache[place]["lon"]

    prompt = f"""
You are an assistant that provides exact geographic coordinates.
Return only JSON with keys "lat" and "lon" for the place: {place}
"""
    try:
        # Run sync OpenAI call in thread for async compatibility
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "You provide accurate latitude and longitude in JSON only."},
                {"role": "user", "content": prompt}
            ]
        )
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        cache[place] = {"lat": float(data["lat"]), "lon": float(data["lon"])}
        GEO_CACHE_FILE.write_text(json.dumps(cache, indent=2))
        return float(data["lat"]), float(data["lon"])
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"OpenAI geocoding failed: {e}")

# -------------------------
# Calculate natal chart
# -------------------------
async def calculate_chart(data: NatalData):
    lat, lon = await geocode_with_openai(data.place)

    try:
        birth_dt = datetime.datetime(data.year, data.month, data.day, data.hour, data.minute)
        jd_ut = swe.julday(birth_dt.year, birth_dt.month, birth_dt.day,
                           birth_dt.hour + birth_dt.minute / 60)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date/time provided.")

    try:
        swe.set_ephe_path(".")
        houses, ascmc = swe.houses(jd_ut, lat, lon, b"P")
    except swe.SweError as e:
        raise HTTPException(status_code=500, detail=f"Swisseph calculation failed: {e}")

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

    asc_sign, asc_deg = deg_to_sign(ascmc[0])
    mc_sign, mc_deg = deg_to_sign(ascmc[1])
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

    with open(USER_CHART_DIR / f"{data.username}.json", "w") as f:
        json.dump(astro_data, f, indent=2)

    return astro_data
