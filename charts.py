# charts.py
import datetime
import json
from pathlib import Path
from fastapi import HTTPException
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import swisseph as swe

USER_CHART_DIR = Path("./user_charts")
USER_CHART_DIR.mkdir(exist_ok=True)

geolocator = Nominatim(user_agent="anlasana_app")

class NatalData:
    def __init__(self, username, year, month, day, hour, minute, place):
        self.username = username
        self.year = year
        self.month = month
        self.day = day
        self.hour = hour
        self.minute = minute
        self.place = place

def deg_to_sign(deg):
    signs = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
             "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
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

    # Save chart locally
    with open(USER_CHART_DIR / f"{data.username}.json", "w") as f:
        json.dump(astro_data, f, indent=2)

    return astro_data
