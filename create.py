from dotenv import load_dotenv
load_dotenv()


import os
import asyncio
from supabase import create_client
import json
from charts import generate_chart_for_user  # Your updated chart.py

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

async def upgrade_user_chart(user):
    user_id = user["id"]
    chart = user.get("chart")
    try:
        needs_update = True

        if chart:
            try:
                chart_data = chart if isinstance(chart, dict) else json.loads(chart)
                planets = chart_data.get("planets", {})
                if "North Node" in planets and "South Node" in planets:
                    needs_update = False
            except Exception:
                needs_update = True

        if needs_update:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    print(f"[Attempt {attempt}] Updating chart for {user_id}...")
                    await generate_chart_for_user(user_id)
                    print(f"✅ Chart upgraded for {user_id}")
                    break
                except Exception as e:
                    print(f"[WARN] Attempt {attempt} failed for {user_id}: {e}")
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        print(f"[ERROR] Failed to update {user_id} after {MAX_RETRIES} attempts")
        else:
            print(f"Chart for {user_id} already has nodes, skipping.")

    except Exception as e:
        print(f"[ERROR] Unexpected error for {user_id}: {e}")

async def upgrade_all_charts():
    resp = supabase.table("users").select("*").execute()
    users = resp.data
    if not users:
        print("No users found.")
        return

    tasks = [upgrade_user_chart(user) for user in users]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(upgrade_all_charts())
