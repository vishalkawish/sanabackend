# helpers.py
from charts import calculate_chart, NatalData
import json
import requests
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

def fetch_user_from_supabase(user_id):
    url = f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}&select=*"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200 or not resp.json():
        return None
    return resp.json()[0]

def save_chart_to_supabase(user_chart, user_id):
    url = f"{SUPABASE_URL}/rest/v1/user_charts"
    payload = {"user_id": user_id, "chart_json": json.dumps(user_chart)}
    requests.post(url, headers=HEADERS, json=payload)

def generate_chart_for_user(user_id):
    user = fetch_user_from_supabase(user_id)
    if not user:
        print(f"User {user_id} not found in Supabase.")
        return None

    if not all([user.get("birthdate"), user.get("birthtime"), user.get("birthplace"), user.get("username")]):
        print(f"User {user['username']} has missing birth info.")
        return None

    birthdate = user["birthdate"]
    birthtime = user["birthtime"]
    year, month, day = map(int, birthdate.split("-"))
    hour, minute, *_ = map(int, birthtime.split(":"))

    natal_data = NatalData(
        username=user["username"],
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        place=user["birthplace"]
    )

    chart = calculate_chart(natal_data)
    print(f"✅ Chart generated for {user['username']}")

    save_chart_to_supabase(chart, user_id)
    return chart

def fetch_user_from_supabase_by_username(username):
    url = f"{SUPABASE_URL}/rest/v1/users?username=eq.{username}&select=*"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200 or not resp.json():
        return None
    return resp.json()[0]
