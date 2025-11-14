import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # Use service_role for write
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ----------- Request Body -----------
class TokenUpdatePayload(BaseModel):
    user_id: str
    device_token: str


# ----------- API Endpoint -----------
@router.post("/update_device_token")
def update_device_token(payload: TokenUpdatePayload):

    # Update the token
    response = supabase.table("users").update({
        "device_token": payload.device_token
    }).eq("id", payload.user_id).execute()

    # If no rows updated → invalid user
    if len(response.data) == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"status": "success", "message": "Device token updated"}
