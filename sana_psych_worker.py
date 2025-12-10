# sana_psych_worker.py
# Handles:
# - Extracting psychological traits from user messages
# - Merging into psych_map
# - Auto-building relationship_profile (28 fields)
# - Embedding psych_map -> psych_vector for matching
# ✅ WITH DETAILED LOGGING

import os
import json
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from supabase import create_client

# -------------------------
# LOGGING SETUP
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("sana-psych")

# -------------------------
# ENV
# -------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
    raise RuntimeError("Missing ENV vars")

client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()
router = APIRouter()

# -------------------------
# MODELS
# -------------------------
class PsychUpdateRequest(BaseModel):
    id: str
    message: str
    name: Optional[str] = None

# -------------------------
# UTILITIES
# -------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def safe_load_json_fragment(text: str) -> Dict:
    if not text or not isinstance(text, str):
        return {}
    try:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {}

async def to_thread_retry(fn, *args, retries=3, backoff=0.4, **kwargs):
    last_exc = None
    for i in range(retries):
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except Exception as e:
            last_exc = e
            log.warning(f"Thread retry {i+1} failed: {e}")
            await asyncio.sleep(backoff * (2 ** i))
    raise last_exc

RELATIONSHIP_KEYS = [
    "moods", "personality_traits", "love_language", "relationship_goals", "interests",
    "red_flags", "green_flags", "attachment_style", "communication_style",
    "conflict_style", "emotional_triggers", "stress_behaviors", "trauma_signals",
    "boundaries", "dealbreakers", "partner_preferences", "affection_style",
    "trust_style", "intimacy_style", "lifestyle_preferences", "values",
    "core_fears", "stability_needs", "compatibility_requirements",
    "likes", "dislikes", "emotional_needs", "emotional_giving_style"
]

# -------------------------
# PROMPTS
# -------------------------
DYNAMIC_EXTRACTOR_SYSTEM = """
You are a psychological inference engine for building meaningful connections.
Extract psychological traits about the USER only.

Return STRICT JSON only:
{
  "extracted_traits": [
    {"key":"...", "value":"...", "confidence": 0.0}
  ]
}
"""

# -------------------------
# LLM
# -------------------------
def _call_chat(payload: Dict[str, Any]):
    return client.chat.completions.create(**payload)

async def call_dynamic_extractor(user_message: str) -> Dict[str, Any]:
    payload = {
        "model": "gpt-5-nano",
        "messages": [
            {"role": "system", "content": DYNAMIC_EXTRACTOR_SYSTEM},
            {"role": "user", "content": user_message}
        ],
    }

    resp = await to_thread_retry(_call_chat, payload)
    text = resp.choices[0].message.content
    log.info(f"RAW DYNAMIC OUTPUT: {text}")

    parsed = safe_load_json_fragment(text)
    return parsed if isinstance(parsed, dict) else {"extracted_traits": []}

# -------------------------
# AUTO RELATIONSHIP BUILDER ✅
# -------------------------
async def auto_route_psych_to_relationship(psych_map: Dict[str, Any]) -> Dict[str, List[str]]:
    base = {k: [] for k in RELATIONSHIP_KEYS}

    system = f"""
Map the psychological traits into this JSON schema:

{json.dumps(base, indent=2)}

Rules:
- No guessing
- No filler values like "unknown"
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

    resp = await to_thread_retry(_call_chat, payload)
    text = resp.choices[0].message.content
    parsed = safe_load_json_fragment(text)

    if isinstance(parsed, dict):
        log.info(f"✅ AUTO RELATIONSHIP PROFILE: {parsed}")
        return parsed

    return base

# -------------------------
# MERGE PSYCH
# -------------------------
def merge_into_psych_map(existing: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
    out = json.loads(json.dumps(existing or {}))
    now = now_iso()

    items = extracted.get("extracted_traits", [])
    log.info(f"TRAITS TO MERGE: {items}")

    for it in items:
        key = (it.get("key") or "").strip().lower().replace(" ", "_")
        val = it.get("value")
        conf = float(it.get("confidence", 0.0))

        if not key or not val:
            continue

        out[key] = {
            "value": val,
            "confidence": conf,
            "history": [{"time": now, "value": val, "confidence": conf}]
        }

    log.info(f"UPDATED PSYCH MAP: {out}")
    return out

# -------------------------
# EMBEDDINGS
# -------------------------
EMBED_MODEL = "text-embedding-3-small"

def embed_sync(text: str) -> List[float]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding

async def embed_and_store_user_vector(user_id: str, psych_map: Dict[str, Any]):
    vector = await asyncio.to_thread(embed_sync, json.dumps(psych_map))

    res = supabase.table("users").update({
        "psych_vector": vector
    }).eq("id", user_id).execute()

    log.info(f"✅ EMBEDDING SAVED: {user_id}")
    log.info(f"SUPABASE VECTOR UPDATE RESPONSE: {res}")

# -------------------------
# MAIN ENDPOINT ✅✅✅
# -------------------------
@router.post("/sana/psych/update")
async def update_psych(data: PsychUpdateRequest):
    user_id = data.id
    user_message = data.message

    log.info(f"🚀 PSYCH UPDATE STARTED: {user_id}")
    log.info(f"USER MESSAGE: {user_message}")

    resp = supabase.table("users").select(
        "id, psych_map, relationship_profile, profile_candidates, profile_versions"
    ).eq("id", user_id).single().execute()

    user = resp.data
    psych_map = user.get("psych_map") or {}
    profile_candidates = user.get("profile_candidates") or []
    profile_versions = user.get("profile_versions") or []

    dynamic_res = await call_dynamic_extractor(user_message)
    updated_psych_map = merge_into_psych_map(psych_map, dynamic_res)

    relationship_profile = await auto_route_psych_to_relationship(updated_psych_map)

    now = now_iso()
    profile_candidates.append({"candidate": dynamic_res, "time": now})
    profile_versions.append({
        "before": psych_map,
        "after": updated_psych_map,
        "candidate": dynamic_res,
        "time": now
    })

    res = supabase.table("users").update({
        "psych_map": updated_psych_map,
        "relationship_profile": relationship_profile,
        "profile_candidates": profile_candidates[-200:],
        "profile_versions": profile_versions[-500:]
    }).eq("id", user_id).execute()

    log.info(f"✅ SUPABASE PSYCH UPDATE RESPONSE: {res}")

    await embed_and_store_user_vector(user_id, updated_psych_map)

    return {
        "status": "ok",
        "user_id": user_id,
        "updated_at": now
    }
