import json, os, requests
from charts import calculate_chart, NatalData

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def fetch_user_from_supabase(user_id: str):
    """Fetch a user from Supabase by id"""
    url = f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}&select=*"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200 or not resp.json():
        return None
    return resp.json()[0]

def save_chart_to_supabase(user_chart: dict, user_id: str):
    """Save chart JSON directly into users.chart column"""
    url = f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}"
    payload = {"chart": json.dumps(user_chart)}
    resp = requests.patch(url, headers=HEADERS, json=payload)
    if resp.status_code not in (200, 204):
        print(f"⚠️ Failed to save chart for {user_id}: {resp.text}")
    else:
        print(f"💾 Chart saved for {user_id}")

# ✅ FIXED: Now async
async def generate_chart_for_user(user: dict):
    """Generate chart for a user if missing"""
    if not user:
        print("⚠️ User not found.")
        return None

    # Skip if chart already exists
    if user.get("chart"):
        print(f"⏩ Chart already exists for {user.get('name')}")
        return json.loads(user["chart"])

    if not all([user.get("birthdate"), user.get("birthtime"), user.get("birthplace")]):
        print(f"⚠️ {user.get('name')} has missing birth info.")
        return None

    # Parse birth info
    year, month, day = map(int, user["birthdate"].split("-"))
    hour, minute, *_ = map(int, user["birthtime"].split(":"))

    natal_data = NatalData(
        id=user["id"],
        name=user.get("name", "Unknown"),
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        place=user["birthplace"]
    )

    # ✅ Await calculate_chart directly (no asyncio.run)
    chart = await calculate_chart(natal_data)
    print(f"✅ Chart generated for {user.get('name')}")

    # Save chart back to Supabase
    save_chart_to_supabase(chart, user["id"])
    return chart
