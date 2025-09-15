# 1️⃣ Load env first
from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, Form, HTTPException
from supabase import create_client
import os

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@router.post("/savePhone")
async def save_phone(userId: str = Form(...), phone: str = Form(...)):
    try:
        supabase.table("users").update({"phone_number": phone}).eq("id", userId).execute()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
