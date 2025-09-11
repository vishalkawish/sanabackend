from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import os
from datetime import datetime, timezone
from typing import Dict
import json

app = FastAPI()
router = APIRouter()

# Supabase config
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# In-memory store of active WebSocket connections
active_connections: Dict[str, WebSocket] = {}

# --- Models ---
class UserAction(BaseModel):
    user_id: str
    target_user_id: str
    action: str  # "skip" or "connect"


# --- Helper to notify user ---
async def notify_user(target_user_id: str, message: dict):
    ws = active_connections.get(target_user_id)
    if ws:
        try:
            await ws.send_text(json.dumps(message))
            print(f"📩 Notified {target_user_id}: {message}")
        except Exception as e:
            print(f"⚠️ Failed to notify {target_user_id}: {e}")
    else:
        # Store for offline delivery
        supabase.table("notifications").insert({
            "user_id": target_user_id,
            "payload": message,
            "delivered": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()


# --- WebSocket endpoint ---
@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    active_connections[user_id] = websocket
    print(f"✅ User {user_id} connected")

    # Send any pending actions (connect requests)
    pending = supabase.table("user_actions") \
        .select("user_id, action") \
        .eq("target_user_id", user_id) \
        .in_("action", ["connect", "matched"]) \
        .execute()

    if pending.data:
        for req in pending.data:
            message = {
                "status": "ok",
                "action": req["action"],
                "matched": req["action"] == "matched",
                "from": req["user_id"],
                "to": user_id
            }
            await notify_user(user_id, message)

    # Send undelivered notifications
    undelivered = supabase.table("notifications") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("delivered", False) \
        .execute()

    if undelivered.data:
        for notif in undelivered.data:
            await notify_user(user_id, notif["payload"])
            # mark delivered
            supabase.table("notifications").update({"delivered": True}).eq("id", notif["id"]).execute()

    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        print(f"❌ User {user_id} disconnected")
        active_connections.pop(user_id, None)


# --- Record user action ---
@router.post("/user_action/")
async def record_action(data: UserAction):
    user_id = data.user_id
    target_user_id = data.target_user_id
    action = data.action.lower()
    now = datetime.now(timezone.utc).isoformat()

    if user_id == target_user_id:
        raise HTTPException(status_code=400, detail="User cannot act on themselves")
    if action not in {"skip", "connect"}:
        raise HTTPException(status_code=400, detail="Invalid action")

    # Check reciprocal connection for match
    reciprocal = supabase.table("user_actions") \
        .select("id, action") \
        .eq("user_id", target_user_id) \
        .eq("target_user_id", user_id) \
        .eq("action", "connect") \
        .execute()

    is_match = bool(reciprocal.data) and action == "connect"

    # Update reciprocal if matched
    if is_match:
        supabase.table("user_actions").update({
            "action": "matched",
            "updated_at": now
        }).eq("user_id", target_user_id).eq("target_user_id", user_id).execute()

    # Upsert current action
    existing = supabase.table("user_actions") \
        .select("id, action") \
        .eq("user_id", user_id) \
        .eq("target_user_id", target_user_id) \
        .execute()

    record_action_value = "matched" if is_match else action

    if existing.data:
        supabase.table("user_actions").update({
            "action": record_action_value,
            "updated_at": now
        }).eq("user_id", user_id).eq("target_user_id", target_user_id).execute()
    else:
        supabase.table("user_actions").insert({
            "user_id": user_id,
            "target_user_id": target_user_id,
            "action": record_action_value,
            "created_at": now,
            "updated_at": now
        }).execute()

    response = {
        "status": "ok",
        "action": record_action_value,
        "matched": is_match,
        "from": user_id,
        "to": target_user_id
    }

    # Notify target user
    await notify_user(target_user_id, response)

    return response


# --- Include router ---
app.include_router(router)
