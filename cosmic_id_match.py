from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx, os
import openai
import json

router = APIRouter()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

class MatchRequest(BaseModel):
    sana_id_1: str
    sana_id_2: str

async def fetch_user(sana_id: str):
    url = f"{SUPABASE_URL}/rest/v1/users?sana_id=eq.{sana_id}&select=*"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    async with httpx.AsyncClient() as client_http:
        resp = await client_http.get(url, headers=headers)
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
        return None

@router.post("/cosmic_id_match")
async def sana_match_opinion(request: MatchRequest):
    user1 = await fetch_user(request.sana_id_1)
    user2 = await fetch_user(request.sana_id_2)

    if not user1 or not user2:
        raise HTTPException(status_code=404, detail="One or both users not found.")

    prompt = f"""
You are Sana, a wise love astrologer and relationship guide.
Give 5 honest match opinions between two users using their info and charts.
- Include challenges, strengths, growth areas, and a tip to make it work.
- Use a human-like tone, avoid astrology jargon.
- The **first point must mention both users by name**, like 'Love compatibility between {user1['name']} and {user2['name']} etc.. make it engaging.'
- Max 1–2 lines per point.
- be realistic and tell directly if they are not a good match.
- End with Sana's super honest advice and tip on their match.


User 1:
Name: {user1['name']}
Birthdate: {user1['birthdate']}
Birthtime: {user1.get('birthtime')}
Birthplace: {user1.get('birthplace')}
Gender: {user1.get('gender')}
Personality traits: {user1.get('personality_traits')}
Love language: {user1.get('love_language')}
Interests: {user1.get('interests')}
Chart: {user1.get('chart')}

User 2:
Name: {user2['name']}
Birthdate: {user2['birthdate']}
Birthtime: {user2.get('birthtime')}
Birthplace: {user2.get('birthplace')}
Gender: {user2.get('gender')}
Personality traits: {user2.get('personality_traits')}
Love language: {user2.get('love_language')}
Interests: {user2.get('interests')}
Chart: {user2.get('chart')}

Each object must have title and content fields.
Format ONLY in JSON as a list of objects like:
[
  {{"title": "...", "content": "..."}}
]
"""


    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[{"role": "user", "content": prompt}],
        )

        reply_text = response.choices[0].message.content.strip()
        return {"sana_opinion": json.loads(reply_text)}


    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")
