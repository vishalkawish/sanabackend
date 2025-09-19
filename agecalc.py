
from dotenv import load_dotenv

# -------------------------
# Load environment variables
# -------------------------
load_dotenv()
import os
from datetime import datetime
from supabase import create_client

# -------------------------
# Supabase setup
# -------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase URL or Key not found in environment variables.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# Helper to calculate age
# -------------------------
def calculate_age(birthdate_str):
    try:
        birthdate = datetime.strptime(birthdate_str, "%Y-%m-%d")
        today = datetime.today()
        age = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
        return age
    except Exception as e:
        print(f"[WARN] Invalid birthdate {birthdate_str}: {e}")
        return None

# -------------------------
# Update all users with age
# -------------------------
def update_ages():
    users = supabase.table("users").select("*").execute().data
    for user in users:
        birthdate_str = user.get("birthdate")
        if not birthdate_str:
            print(f"[SKIP] No birthdate for user {user.get('id')}")
            continue

        age = calculate_age(birthdate_str)
        if age is None:
            continue

        supabase.table("users").update({"age": age}).eq("id", user["id"]).execute()
        print(f"[INFO] Updated age for {user.get('name')} ({user.get('id')}) => {age}")

if __name__ == "__main__":
    update_ages()
    print("✅ All users updated with age.")
