import datetime
import json
from pathlib import Path
from fastapi import HTTPException
import swisseph as swe
import os
from dotenv import load_dotenv
from openai import OpenAI
import asyncio
from supabase import create_client
from dataclasses import dataclass

# -------------------------
# Load environment variables
# -------------------------
load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OpenAI API key not found. Set OPENAI_API_KEY in .env")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase URL or Key not found in .env")

client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# Directories
# -------------------------
USER_CHART_DIR = Path("./user_charts")
USER_CHART_DIR.mkdir(exist_ok=True)

GEO_CACHE_FILE = Path("./geo_cache.json")
if not GEO_CACHE_FILE.exists():
    GEO_CACHE_FILE.write_text("{}")

# -------------------------
# Natal data structure
# -------------------------
@dataclass
class NatalData:
    id: str
    name: str
    year: int
    month: int
    day: int
    hour: int
    minute: int
    place: str

# -------------------------
# Utility functions
# -------------------------
def deg_to_sign(deg: float):
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
        if name.startswith("_"):  # skip temporary keys
            continue
        if isinstance(deg, dict) and "longitude" in deg:
            signed[name] = deg
            continue
        if deg is not None:
            sign, deg_in_sign = deg_to_sign(deg)
            signed[name] = {
                "longitude": round(deg, 2),
                "sign": sign,
                "deg_in_sign": deg_in_sign
            }
        else:
            signed[name] = {"longitude": None, "sign": None, "deg_in_sign": None}
    return signed

# -------------------------
# Async geocoding
# -------------------------
async def geocode_with_openai(place: str):
    cache = json.loads(GEO_CACHE_FILE.read_text())
    if place in cache:
        return cache[place]["lat"], cache[place]["lon"]

    prompt = f"Return JSON with lat and lon for place: {place}"
    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "Provide only latitude and longitude in JSON."},
                {"role": "user", "content": prompt}
            ]
        )
        text = resp.choices[0].message.content.strip().replace("```json","").replace("```","").strip()
        data = json.loads(text)
        lat, lon = float(data["lat"]), float(data["lon"])
        cache[place] = {"lat": lat, "lon": lon}
        GEO_CACHE_FILE.write_text(json.dumps(cache, indent=2))
        return lat, lon
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Geocoding failed: {e}")

# -------------------------
# Add nodes
# -------------------------
def add_nodes(planets, jd_ut):
    try:
        n_lon, _ = swe.calc_ut(jd_ut, swe.MEAN_NODE)
        n_lon = n_lon[0]
        s_lon = (n_lon + 180) % 360

        n_sign, n_deg = deg_to_sign(n_lon)
        s_sign, s_deg = deg_to_sign(s_lon)

        planets["North Node"] = {"longitude": round(n_lon, 2), "sign": n_sign, "deg_in_sign": n_deg}
        planets["South Node"] = {"longitude": round(s_lon, 2), "sign": s_sign, "deg_in_sign": s_deg}
    except Exception as e:
        print(f"[WARN] Node calculation failed: {e}")
    return planets

# -------------------------
# Calculate natal chart
# -------------------------
async def calculate_chart(data: NatalData):
    lat, lon = await geocode_with_openai(data.place)

    try:
        birth_dt = datetime.datetime(data.year, data.month, data.day, data.hour, data.minute)
        jd_ut = swe.julday(
            birth_dt.year, birth_dt.month, birth_dt.day,
            birth_dt.hour + birth_dt.minute / 60
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date/time provided.")

    try:
        swe.set_ephe_path(".")
        houses, ascmc = swe.houses(jd_ut, lat, lon, b"P")
    except swe.SweError as e:
        raise HTTPException(status_code=500, detail=f"Swisseph failed: {e}")

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

    # Ascendant & Midheaven
    asc_sign, asc_deg = deg_to_sign(ascmc[0])
    mc_sign, mc_deg = deg_to_sign(ascmc[1])

    # Add nodes
    planets = add_nodes(planets, jd_ut)

    # Planets with signs
    planets_signed = planets_with_signs(planets)

    # Full chart
    chart = {
        "id": data.id,
        "name": data.name,
        "place": data.place,
        "lat": lat,
        "lon": lon,
        "birthdate": birth_dt.date().isoformat(),
        "birthtime": birth_dt.time().isoformat(timespec="minutes"),
        "julian_day": jd_ut,
        "ascendant": {"longitude": round(ascmc[0], 2), "sign": asc_sign, "deg_in_sign": asc_deg},
        "midheaven": {"longitude": round(ascmc[1], 2), "sign": mc_sign, "deg_in_sign": mc_deg},
        "houses": [round(h, 2) for h in houses],
        "planets": planets_signed,
        "north_node": planets_signed["North Node"],
        "south_node": planets_signed["South Node"]
    }

    # Save locally
    with open(USER_CHART_DIR / f"{data.id}.json", "w") as f:
        json.dump(chart, f, indent=2)

    # Save to Supabase
    supabase.table("users").update({"chart": json.dumps(chart)}).eq("id", data.id).execute()

    return chart

# -------------------------
# Generate chart for user
# -------------------------
async def generate_chart_for_user(user_id: str):
    resp = supabase.table("users").select("*").eq("id", user_id).single().execute()
    user = resp.data
    if not user:
        raise ValueError(f"No user found with id {user_id}")

    birth = user["birth"]
    data = NatalData(
        id=user_id,
        name=user.get("name", "Unknown"),
        year=birth["year"],
        month=birth["month"],
        day=birth["day"],
        hour=birth.get("hour", 0),
        minute=birth.get("minute", 0),
        place=birth["place"]
    )
    return await calculate_chart(data)
