from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import os
from datetime import datetime, timezone
from typing import Dict

router = APIRouter()

# Supabase config
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# In-memory store of active connections
active_connections: Dict[str, WebSocket] = {}


class UserAction(BaseModel):
    user_id: str
    target_user_id: str
    action: str  # "skip" or "connect"


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """Each user connects here and we keep their WebSocket reference."""
    await websocket.accept()
    active_connections[user_id] = websocket
    print(f"✅ User {user_id} connected")

    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        print(f"❌ User {user_id} disconnected")
        active_connections.pop(user_id, None)


@router.post("/user_action/")
def record_action(data: UserAction):
    try:
        user_id = data.user_id
        target_user_id = data.target_user_id
        action = data.action.lower()

        if user_id == target_user_id:
            raise HTTPException(status_code=400, detail="User cannot act on themselves")

        if action not in {"skip", "connect"}:
            raise HTTPException(status_code=400, detail="Invalid action")

        now = datetime.now(timezone.utc).isoformat()  # ✅ convert to string

        # Check reciprocal connection
        reciprocal = (
            supabase.table("user_actions")
            .select("id, action")
            .eq("user_id", target_user_id)
            .eq("target_user_id", user_id)
            .eq("action", "connect")
            .execute()
        )

        is_match = False
        if reciprocal.data and action == "connect":
            is_match = True
            supabase.table("user_actions").update(
                {"action": "matched", "updated_at": now}
            ).eq("user_id", target_user_id).eq("target_user_id", user_id).execute()

        # Check if current record exists
        existing = (
            supabase.table("user_actions")
            .select("id, action")
            .eq("user_id", user_id)
            .eq("target_user_id", target_user_id)
            .execute()
        )

        if existing.data:
            supabase.table("user_actions").update(
                {"action": "matched" if is_match else action, "updated_at": now}
            ).eq("user_id", user_id).eq("target_user_id", target_user_id).execute()
        else:
            supabase.table("user_actions").insert(
                {
                    "user_id": user_id,
                    "target_user_id": target_user_id,
                    "action": "matched" if is_match else action,
                    "created_at": now,
                    "updated_at": now,
                }
            ).execute()

        response = {
            "status": "ok",
            "action": "matched" if is_match else action,
            "matched": is_match,
            "from": user_id,
            "to": target_user_id,
        }

        # 🔥 Notify the target user if online
        if target_user_id in active_connections:
            import json
            ws = active_connections[target_user_id]
            try:
                ws.send_text(json.dumps(response))
                print(f"📩 Notified {target_user_id}: {response}")
            except Exception as e:
                print(f"⚠️ Failed to notify {target_user_id}: {e}")

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
