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
    cosmic_id_1: str
    cosmic_id_2: str

async def fetch_user(cosmic_id: str):
    url = f"{SUPABASE_URL}/rest/v1/users?cosmic_id=eq.{cosmic_id}&select=*"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    async with httpx.AsyncClient() as client_http:
        resp = await client_http.get(url, headers=headers)
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
        return None

@router.post("/cosmic_id_match")
async def sana_match_opinion(request: MatchRequest):
    user1 = await fetch_user(request.cosmic_id_1)
    user2 = await fetch_user(request.cosmic_id_2)

    if not user1 or not user2:
        raise HTTPException(status_code=404, detail="One or both users not found.")

    prompt = f"""
    You are Sana, a wise love astrologer and relationship guide.
    Give 5 honest match opinion between two users using their info and charts.
    include challanges, strengths, and growth areas, tip to make it work.
    use human like tone. avoid astrology jargon.
    Below is two users info: Use the practical details(personality_traits, love_language, interest) to form your opinion. and only use the charts to 
    read their hearts desires and emotional needs.
    max 1-2 lines per point.
    and end it with sana super honest advice and tip on their match.
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
    Each object must have title and content fields
    Format ONLY in JSON as:
    {{"title": "...", "content": "..."}}
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
