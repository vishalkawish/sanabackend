import os, asyncio
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)
router = APIRouter()


class SanaGreetingRequest(BaseModel):
    name: str


async def call_openai_async(prompt: str, system_msg: str):
    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=1  # gives random tone variations
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sana AI error: {e}")


@router.post("/sana/greeting")
async def sana_dynamic_greeting(data: SanaGreetingRequest):
    name = data.name.strip() or "there"
    now = datetime.now()
    hour = now.hour

    # Determine time of day
    if hour < 12:
        time_period = "morning"
    elif hour < 17:
        time_period = "afternoon"
    elif hour < 21:
        time_period = "evening"
    else:
        time_period = "night"

    # --- Sana prompt ---
    prompt = f"""
It's {time_period}. User name: {name}.
You're sana...Greet the user naturally to make user feel energetic..say sweet nickanmes...make it short".
"""

    greeting = await call_openai_async(prompt, "You are Sana, a greeting exert ai.")
    return {"greeting": greeting, "time_period": time_period}
