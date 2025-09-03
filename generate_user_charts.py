# generate_user_charts.py
import os
import json
import requests
import shutil
from datetime import datetime
from main import calculate_chart, NatalData, USER_CHART_DIR
from dotenv import load_dotenv

# ---------------------------
# Load environment
# ---------------------------
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL or SUPABASE_KEY not set in environment.")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

# ---------------------------
# Clean old charts
# ---------------------------
if USER_CHART_DIR.exists():
    shutil.rmtree(USER_CHART_DIR)  # delete everything
USER_CHART_DIR.mkdir(parents=True, exist_ok=True)  # recreate clean folder

print("🧹 Old charts deleted, fresh start...")

# ---------------------------
# Fetch users from Supabase
# ---------------------------
resp = requests.get(f"{SUPABASE_URL}/rest/v1/users?select=*", headers=headers)
if resp.status_code != 200:
    raise RuntimeError(f"Failed to fetch users from Supabase: {resp.text}")

users = resp.json()
print(f"Found {len(users)} users.")

# ---------------------------
# Generate charts
# ---------------------------
for user in users:
    try:
        # Skip if any required field is missing/null
        if not user.get("name") or not user.get("birthdate") or not user.get("birthtime") or not user.get("birthplace"):
            print(f"⏩ Skipping {user.get('id', 'unknown')} due to missing fields.")
            continue

        # Parse birthdate and birthtime safely
        try:
            bdate = datetime.strptime(user["birthdate"], "%Y-%m-%d")
            btime = datetime.strptime(user["birthtime"], "%H:%M:%S")
        except Exception:
            print(f"⏩ Skipping {user.get('name','unknown')} due to invalid date/time format.")
            continue

        natal_data = NatalData(
            username=user["name"],
            year=bdate.year,
            month=bdate.month,
            day=bdate.day,
            hour=btime.hour,
            minute=btime.minute,
            place=user["birthplace"]
        )

        # Generate and save chart
        calculate_chart(natal_data)
        print(f"✅ Chart generated for {user['name']}")

    except Exception as e:
        print(f"❌ Failed for user {user.get('name','unknown')}: {e}")

print("✅ All user charts regenerated successfully!")
