# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ValidationError
import swisseph as swe
import datetime
import os
import openai
import json
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Rest of your code...
# ...
# ---------------------------
# Init
# ---------------------------
app = FastAPI()
# Use a more descriptive user agent for geocoding requests
geolocator = Nominatim(user_agent="anlasana-astro-api")

# OpenAI key from environment
openai.api_key = os.environ.get("OPENAI_API_KEY")
if not openai.api_key:
    # Use HTTPException for a clean, user-friendly error response
    raise HTTPException(status_code=500, detail="OpenAI API key not found. Set environment variable OPENAI_API_KEY")

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
    place: str  # Example: "Delhi"

# ---------------------------
# Routes
# ---------------------------
@app.get("/")
def home():
    return {"message": "✨ Anlasana backend is running 🚀"}

@app.post("/astro/natal")
def get_natal_chart(data: NatalData):
    try:
        # 1. Convert place → lat/lon with proper error handling
        try:
            location = geolocator.geocode(data.place, timeout=10) # Added timeout
            if not location:
                raise HTTPException(status_code=404, detail=f"❌ Place not found: {data.place}")
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            raise HTTPException(status_code=503, detail=f"Geocoding service unavailable: {e}")

        lat, lon = float(location.latitude), float(location.longitude)

        # 2. Convert DOB/TIME → Julian Day
        try:
            birth_dt = datetime.datetime(
                data.year, data.month, data.day, data.hour, data.minute
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date/time provided.")

        jd_ut = swe.julday(
            birth_dt.year,
            birth_dt.month,
            birth_dt.day,
            birth_dt.hour + birth_dt.minute / 60.0
        )

        # 3. Calculate houses (Placidus)
        # Using a try-except block for swisseph calculations for robustness
        try:
            houses, ascmc = swe.houses(jd_ut, lat, lon, b"P")
        except swe.SweError as e:
            raise HTTPException(status_code=500, detail=f"Swisseph calculation failed: {e}")

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
        # AI Interpretation (OpenAI >=1.0.0)
        # ---------------------------
        # Pass the calculated astro_data to the AI
        prompt_content = f"""
You are Sana, an emotional mirror and master astrologer.
Use the following natal chart data to generate a fully personalized,
easy-to-understand soul reading for the user.
The reading should be warm, gentle, and emotional in tone.

User's Name: {data.username}
Natal Chart Data:
{json.dumps(astro_data, indent=2)}

Generate 10–12 sections in JSON format only.
Example format:
{{ "sections": [ {{ "title": "Your Sun Sign", "content": "The sun reveals your core identity. Your Sun in {astro_data['planets']['Sun']} shows..." }}, ... ] }}

Important:
- Provide PURE JSON output only. Do not include any markdown, prose, or extra text before or after the JSON.
- Each content section should be 1-3 sentences max.
- The reading must feel personal and directly address the user.
"""
        
        # Add new try-except block for the OpenAI API call
        try:
            ai_response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are Sana, a soulful astrology guide who outputs PURE JSON."},
                    {"role": "user", "content": prompt_content}
                ],
                temperature=0.8,
                response_format={"type": "json_object"}
            )
            # Check if the response is valid before accessing attributes
            if ai_response and ai_response.choices:
                reflection = ai_response.choices[0].message.content
            else:
                # Handle cases where the response object is empty or unexpected
                raise HTTPException(status_code=500, detail="OpenAI API call returned an invalid response.")

        except openai.OpenAIError as e:
            # Catch specific OpenAI API errors and provide a clear message
            raise HTTPException(status_code=500, detail=f"OpenAI API error: {e}")
        
    except HTTPException as e:
        # Re-raise the HTTPException to be handled by FastAPI
        raise e
    except Exception as e:
        # Catch any other unexpected errors and return a 500 status code
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

    return {
        "astro_data": astro_data,
        "reflection": reflection
    }