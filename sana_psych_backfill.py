from dotenv import load_dotenv
load_dotenv()
import os
import json
import asyncio
import logging
from typing import Dict, Any, List

import openai
from supabase import create_client

# ----------------------------------------------------
# CONFIG
# ----------------------------------------------------
MAX_WORKERS = 20   # ⚡ SUPER FAST — 20 concurrent LLM tasks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("sana-backfill")

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
openai.api_key = OPENAI_API_KEY

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

semaphore = asyncio.Semaphore(MAX_WORKERS)

# ----------------------------------------------------
# RELATIONSHIP SCHEMA
# ----------------------------------------------------
REL_KEYS = [
    "moods", "personality_traits", "love_language", "relationship_goals", "interests",
    "red_flags", "green_flags", "attachment_style", "communication_style",
    "conflict_style", "emotional_triggers", "stress_behaviors", "trauma_signals",
    "boundaries", "dealbreakers", "partner_preferences", "affection_style",
    "trust_style", "intimacy_style", "lifestyle_preferences", "values",
    "core_fears", "stability_needs", "compatibility_requirements",
    "likes", "dislikes", "emotional_needs", "emotional_giving_style"
]

def is_empty_psych_map(value):
    return (not value) or (isinstance(value, dict) and len(value) == 0)

# ----------------------------------------------------
# NORMALIZE CHAT HISTORY -> CLEAN STRING
# ----------------------------------------------------
def normalize_chat_history(raw):
    """
    Converts JSON array chat_history into a single clean string.
    Only USER messages are used.
    """
    if not raw:
        return ""

    try:
        # If already a Python list
        if isinstance(raw, list):
            msgs = raw
        else:
            msgs = json.loads(raw)
    except Exception:
        return ""

    lines = []
    for m in msgs:
        if m.get("role") == "user":
            text = m.get("content", "")
            if text:
                lines.append(text)

    return "\n".join(lines)


# ----------------------------------------------------
# OPENAI WRAPPERS (with retry & JSON safety)
# ----------------------------------------------------
def call_llm(payload: Dict[str, Any]):
    return openai.ChatCompletion.create(**payload)

async def safe_llm_call(payload, label="LLM"):
    """Retries, extracts JSON, never crashes."""
    for attempt in range(3):
        try:
            async with semaphore:
                resp = await asyncio.to_thread(call_llm, payload)

            text = resp["choices"][0]["message"]["content"] or ""

            log.info(f"{label} RAW (attempt {attempt+1}): {text[:200]}")

            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end <= start:
                raise ValueError("No JSON in output")

            return json.loads(text[start:end])

        except Exception as e:
            log.error(f"{label} failed attempt {attempt+1}: {e}")
            await asyncio.sleep(0.5 * (attempt + 1))

    log.error(f"{label} FAILED ALL ATTEMPTS — using fallback")
    return {"extracted_traits": []} if label == "EXTRACT" else {k: [] for k in REL_KEYS}


# ----------------------------------------------------
# EXTRACT TRAITS → LLM
# ----------------------------------------------------
async def extract_traits(chats: str):
    payload = {
        "model": "gpt-5-nano",
        "messages": [
            {
                "role": "system",
                "content": """
Extract psychological traits about the USER only.
Return STRICT JSON:
{
 "extracted_traits":[{"key":"...","value":"...","confidence":0.0}]
}
"""
            },
            {
                "role": "user",
                "content": chats
            }
        ],
    }
    return await safe_llm_call(payload, label="EXTRACT")


# ----------------------------------------------------
# ROUTE TRAITS → RELATIONSHIP PROFILE
# ----------------------------------------------------
async def route_relationship(ps_map: Dict[str, Any]):
    base_schema = {k: [] for k in REL_KEYS}

    payload = {
        "model": "gpt-5-nano",
        "messages": [
            {
                "role": "system",
                "content": f"""
Map traits into this schema:
{json.dumps(base_schema, indent=2)}

Rules:
- STRICT JSON
- No guessing
- 1–3 word values only
"""
            },
            {"role": "user", "content": json.dumps(ps_map)}
        ],
    }

    return await safe_llm_call(payload, label="ROUTE")


# ----------------------------------------------------
# EMBEDDING FUNCTION
# ----------------------------------------------------
def embed_sync(text: str):
    resp = openai.Embedding.create(
        model="text-embedding-3-small",
        input=text
    )
    return resp["data"][0]["embedding"]


# ----------------------------------------------------
# MERGE TRAITS
# ----------------------------------------------------
def merge_traits(existing: dict, traits: List[Dict]):
    updated = existing or {}
    for t in traits:
        key = t.get("key", "").strip().lower().replace(" ", "_")
        val = t.get("value")
        conf = float(t.get("confidence", 0.0))
        if key and val:
            updated[key] = {"value": val, "confidence": conf}
    return updated


# ----------------------------------------------------
# USER WORKER — RUNS IN PARALLEL ⚡⚡⚡
# ----------------------------------------------------
async def process_user(user):
    user_id = user["id"]
    raw_chat = user.get("chat_history") or ""
    chats = normalize_chat_history(raw_chat)

    psych_map = user.get("psych_map") or {}

    # Skip completely empty users
    if is_empty_psych_map(psych_map) and not chats:
        log.info(f"SKIPPED (no psych + no chat): {user_id}")
        return

    # Build psych map from chat if empty
    if is_empty_psych_map(psych_map):
        log.info(f"Extracting traits from chat: {user_id}")
        extracted = await extract_traits(chats)
        psych_map = merge_traits({}, extracted.get("extracted_traits", []))

    # Build relationship profile
    relationship_profile = await route_relationship(psych_map)

    # Vector embeddings
    vector = await asyncio.to_thread(embed_sync, json.dumps(psych_map))

    # Save to DB
    supabase.table("users").update({
        "psych_map": psych_map,
        "relationship_profile": relationship_profile,
        "psych_vector": vector
    }).eq("id", user_id).execute()

    log.info(f"UPDATED: {user_id}")


# ----------------------------------------------------
# MAIN PARALLEL RUNNER
# ----------------------------------------------------
async def run_backfill():
    log.info("🚀 Starting 20× parallel backfill...")

    resp = supabase.table("users").select("id, psych_map, chat_history").execute()
    users = resp.data or []

    tasks = [process_user(u) for u in users]
    await asyncio.gather(*tasks)

    log.info("🎯 Backfill complete — SUPER FAST MODE")


# ----------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------
if __name__ == "__main__":
    asyncio.run(run_backfill())
