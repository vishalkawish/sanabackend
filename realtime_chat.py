# server.py
from fastapi import FastAPI, WebSocket
from supabase import create_client, Client
import os, json, asyncio

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

connected_users = {}  # { user_id: websocket }

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
