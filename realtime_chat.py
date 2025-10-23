# server.py
from fastapi import FastAPI, WebSocket, Query
from supabase import create_client, Client
import os, json, asyncio

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

connected_users = {}  # { user_id: websocket }

# WebSocket endpoint (already exists)
@app.websocket("/ws/{user_id}")
async def chat_socket(websocket: WebSocket, user_id: str):
    await websocket.accept()
    connected_users[user_id] = websocket

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Save to Supabase
            supabase.table("messages").insert({
                "sender_id": message["sender_id"],
                "receiver_id": message["receiver_id"],
                "content": message["content"]
            }).execute()

            # Forward message to receiver
            receiver_ws = connected_users.get(message["receiver_id"])
            if receiver_ws:
                await receiver_ws.send_text(json.dumps(message))

    except Exception as e:
        print(f"Disconnected: {user_id} ({e})")
    finally:
        del connected_users[user_id]

# 
@app.get("/get_messages")
async def get_messages(user1: str = Query(...), user2: str = Query(...)):
    try:
        # ✅ Fixed OR syntax
        or_filter = f"and(sender_id.eq.{user1},receiver_id.eq.{user2}),and(sender_id.eq.{user2},receiver_id.eq.{user1})"

        result = (
            supabase.table("messages")
            .select("*")
            .or_(or_filter)
            .order("created_at")
            .execute()
        )

        return result.data or []

    except Exception as e:
        return {"error": str(e)}


