# server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import os, json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚡ allow all external devices
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

connected_users = {}  # { user_id: websocket }

# -------------------- WebSocket --------------------
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

            # Forward message to receiver if connected
            receiver_ws = connected_users.get(message["receiver_id"])
            if receiver_ws:
                await receiver_ws.send_text(json.dumps(message))

    except Exception as e:
        print(f"Disconnected: {user_id} ({e})")
    finally:
        del connected_users[user_id]

# -------------------- Get all messages between two users --------------------
@app.get("/get_messages")
async def get_messages(user1: str = Query(...), user2: str = Query(...)):
    try:
        or_filter = f"and(sender_id.eq.{user1},receiver_id.eq.{user2}),and(sender_id.eq.{user2},receiver_id.eq.{user1})"
        result = (
            supabase.table("messages")
            .select("*")
            .or_(or_filter)
            .order("created_at")
            .execute()
        )
        return {"messages": result.data or []}
    except Exception as e:
        return {"error": str(e)}

# -------------------- Get user chat previews --------------------
@app.get("/get_user_chats")
async def get_user_chats(user_id: str = Query(...)):
    try:
        # Fetch messages where user is sender or receiver, newest first
        messages_resp = (
            supabase.table("messages")
            .select("*")
            .or_(f"sender_id.eq.{user_id},receiver_id.eq.{user_id}")
            .order("created_at", desc=True)
            .execute()
        )
        messages = messages_resp.data or []

        # Keep only latest message per soulmate
        chat_dict = {}
        for msg in messages:
            soulmate_id = msg["receiver_id"] if msg["sender_id"] == user_id else msg["sender_id"]

            if soulmate_id not in chat_dict:
                # Fetch soulmate info from users table
                user_resp = supabase.table("users").select("*").eq("id", soulmate_id).execute()
                user_data = user_resp.data[0] if user_resp.data else {}

                chat_dict[soulmate_id] = {
                    "soulmate_id": soulmate_id,
                    "soulmate_name": user_data.get("name", "Unknown"),
                    "last_message": msg["content"],
                    "profile_url": user_data.get("profilePicUrl")
                }

        chats = list(chat_dict.values())
        return {"chats": chats}

    except Exception as e:
        return {"chats": [], "error": str(e)}
