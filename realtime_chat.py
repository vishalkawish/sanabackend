# server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import os, json
import requests
from google.oauth2 import service_account
import google.auth.transport.requests
import io

# -------------------- SETUP --------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
FCM_SERVICE_ACCOUNT_JSON = os.getenv("FCM_SERVICE_ACCOUNT_JSON")  # JSON as one-line env var
PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")  # Firebase project ID

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
connected_users = {}  # { user_id: websocket }

# -------------------- FCM PUSH (HTTP v1 API) --------------------
def get_fcm_access_token():
    # Load service account from environment variable
    json_file = io.StringIO(FCM_SERVICE_ACCOUNT_JSON)
    credentials = service_account.Credentials.from_service_account_info(
        json.load(json_file),
        scopes=["https://www.googleapis.com/auth/firebase.messaging"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token

def send_push_notification(device_token: str, title: str, body: str):
    if not device_token:
        return
    access_token = get_fcm_access_token()
    url = f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send"
    message = {
        "message": {
            "token": device_token,
            "notification": {"title": title, "body": body},
            "android": {"priority": "high"},
            "apns": {"headers": {"apns-priority": "10"}}
        }
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; UTF-8"
    }
    response = requests.post(url, headers=headers, json=message)
    print("📨 Push result:", response.text)

# -------------------- WEBSOCKET --------------------
@app.websocket("/ws/{user_id}")
async def chat_socket(websocket: WebSocket, user_id: str):
    await websocket.accept()
    connected_users[user_id] = websocket
    print(f"✅ User connected: {user_id}")

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Save message to Supabase
            supabase.table("messages").insert({
                "sender_id": message["sender_id"],
                "receiver_id": message["receiver_id"],
                "content": message["content"]
            }).execute()

            receiver_id = message["receiver_id"]
            receiver_ws = connected_users.get(receiver_id)

            if receiver_ws:
                await receiver_ws.send_text(json.dumps(message))
            else:
                res = supabase.table("users").select("device_token, name").eq("id", receiver_id).execute()
                if res.data:
                    device_token = res.data[0].get("device_token")
                    sender_res = supabase.table("users").select("name").eq("id", message["sender_id"]).execute()
                    sender_name = sender_res.data[0]["name"] if sender_res.data else "Someone"
                    send_push_notification(
                        device_token=device_token,
                        title=f"💌 New message from {sender_name}",
                        body=message["content"]
                    )

    except WebSocketDisconnect:
        print(f"❌ User disconnected: {user_id}")
    finally:
        connected_users.pop(user_id, None)

# -------------------- Get all messages --------------------
@app.get("/get_messages")
async def get_messages(user1: str = Query(...), user2: str = Query(...)):
    try:
        or_filter = f"and(sender_id.eq.{user1},receiver_id.eq.{user2}),and(sender_id.eq.{user2},receiver_id.eq.{user1})"
        result = supabase.table("messages").select("*").or_(or_filter).order("created_at").execute()
        return {"messages": result.data or []}
    except Exception as e:
        return {"error": str(e)}

# -------------------- Get user chat previews --------------------
@app.get("/get_user_chats")
async def get_user_chats(user_id: str = Query(...)):
    try:
        messages_resp = supabase.table("messages") \
            .select("*") \
            .or_(f"sender_id.eq.{user_id},receiver_id.eq.{user_id}") \
            .order("created_at", desc=True) \
            .execute()
        messages = messages_resp.data or []

        # 1. Identify all unique soulmate IDs
        soulmate_ids = set()
        for msg in messages:
            sid = msg["receiver_id"] if msg["sender_id"] == user_id else msg["sender_id"]
            soulmate_ids.add(sid)

        # 2. Batch fetch user details in ONE query
        user_map = {}
        if soulmate_ids:
            users_resp = supabase.table("users").select("id, name, profilePicUrl").in_("id", list(soulmate_ids)).execute()
            for u in (users_resp.data or []):
                user_map[u["id"]] = u

        # 3. Build chat previews
        chat_dict = {}
        for msg in messages:
            soulmate_id = msg["receiver_id"] if msg["sender_id"] == user_id else msg["sender_id"]
            if soulmate_id not in chat_dict:
                user_data = user_map.get(soulmate_id, {})
                chat_dict[soulmate_id] = {
                    "soulmate_id": soulmate_id,
                    "soulmate_name": user_data.get("name", "Unknown"),
                    "last_message": msg["content"],
                    "from_self": msg["sender_id"] == user_id,
                    "profile_url": user_data.get("profilePicUrl")
                }

        return {"chats": list(chat_dict.values())}
    except Exception as e:
        return {"chats": [], "error": str(e)}
