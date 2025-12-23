
from dotenv import load_dotenv
load_dotenv()
import os
import json
import asyncio
import logging
from typing import Dict, Any, List

import openai
from supabase import create_client

# -------------------------
# CONFIG ✅
# -------------------------
MAX_CONCURRENT_WORKERS = 10   # 🔥 10x speed

# -------------------------
# LOGGING
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("sana-parallel-builder")

# -------------------------
# ENV
# -------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
    raise RuntimeError("Missing ENV vars")

openai.api_key = OPENAI_API_KEY
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# RELATIONSHIP SCHEMA
# -------------------------
RELATIONSHIP_KEYS = [
    "moods", "personality_traits", "love_language", "relationship_goals", "interests",
    "red_flags", "green_flags", "attachment_style", "communication_style",
    "conflict_style", "emotional_triggers", "stress_behaviors", "trauma_signals",
    "boundaries", "dealbreakers", "partner_preferences", "affection_style",
    "trust_style", "intimacy_style", "lifestyle_preferences", "values",
    "core_fears", "stability_needs", "compatibility_requirements",
    "likes", "dislikes", "emotional_needs", "emotional_giving_style"
]

BASE_PROFILE = {k: [] for k in RELATIONSHIP_KEYS}

# ✅ Correct semaphore (NO external modules)
semaphore = asyncio.Semaphore(MAX_CONCURRENT_WORKERS)

# -------------------------
# GPT CALL ✅ (LEGACY SDK SAFE)
# -------------------------
def call_llm(payload: Dict[str, Any]):
    return openai.ChatCompletion.create(**payload)

async def auto_route_psych_to_relationship(psych_map: Dict[str, Any]) -> Dict[str, List[str]]:
    system = f"""
Map the psychological traits into this JSON schema:

{json.dumps(BASE_PROFILE, indent=2)}

Rules:
- No guessing
- No filler values
- 1–3 word values only
- STRICT JSON only
"""

    payload = {
        "model": "gpt-5-nano",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(psych_map)}
        ],
    }

    try:
        async with semaphore:
            resp = await asyncio.to_thread(call_llm, payload)
            text = resp["choices"][0]["message"]["content"]

        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])

    except Exception as e:
        log.error(f"❌ GPT FAILED: {e}")
        return BASE_PROFILE

# -------------------------
# USER WORKER ✅
# -------------------------
async def process_user(user: Dict[str, Any], stats: Dict[str, int]):
    user_id = user.get("id")
    psych_map = user.get("psych_map") or {}

    if not psych_map:
        log.warning(f"⚠️ SKIPPED: {user_id}")
        stats["skipped"] += 1
        return

    log.info(f"🧠 PROCESSING: {user_id}")

    profile = await auto_route_psych_to_relationship(psych_map)

    supabase.table("users").update({
        "relationship_profile": profile
    }).eq("id", user_id).execute()

    log.info(f"✅ UPDATED: {user_id}")
    stats["updated"] += 1

# -------------------------
# MAIN PARALLEL RUNNER 🚀
# -------------------------
async def rebuild_all_parallel():
    log.info("🚀 STARTING PARALLEL RELATIONSHIP PROFILE REBUILD")

    resp = supabase.table("users").select(
        "id, psych_map"
    ).execute()

    users = resp.data or []
    total = len(users)

    stats = {
        "total": total,
        "updated": 0,
        "skipped": 0
    }

    log.info(f"👥 USERS FOUND: {total}")
    log.info(f"⚡ MAX CONCURRENCY: {MAX_CONCURRENT_WORKERS}")

    tasks = [process_user(user, stats) for user in users]
    await asyncio.gather(*tasks)

    log.info("🎯 PARALLEL REBUILD COMPLETE")
    log.info(f"✅ UPDATED: {stats['updated']}")
    log.info(f"⚠️ SKIPPED: {stats['skipped']}")
    log.info(f"👥 TOTAL: {stats['total']}")

# -------------------------
# ENTRY POINT ✅
# -------------------------
if __name__ == "__main__":
    asyncio.run(rebuild_all_parallel())
