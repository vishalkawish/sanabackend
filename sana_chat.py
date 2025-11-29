# sana_dynamic.py
import os
import json
import re
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List

from fastapi import FastAPI, APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from supabase import create_client

# -------------------------
# ENV
# -------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
    raise RuntimeError("Missing OPENAI_API_KEY or SUPABASE_URL or SUPABASE_KEY env vars")

client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()
router = APIRouter()

# -------------------------
# Models
# -------------------------
class SanaChatMessage(BaseModel):
    id: str
    name: str
    message: str

# -------------------------
# Utilities
# -------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def safe_load_json_fragment(text: str) -> Dict:
    """Extract first {...} JSON object from text and parse it safely."""
    try:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        print("safe_load_json_fragment error:", e)
    return {}

async def to_thread_retry(fn, *args, retries=3, backoff=0.4, **kwargs):
    last_exc = None
    for i in range(retries):
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except Exception as e:
            last_exc = e
            await asyncio.sleep(backoff * (2 ** i))
    raise last_exc

# -------------------------
# LLM Prompts (dynamic extractor + reply)
# -------------------------
DYNAMIC_EXTRACTOR_SYSTEM = """
You are a psychological inference engine. Extract ANY meaningful psychological information from the user's message.
You may CREATE NEW TRAIT CATEGORIES automatically when useful (like "goal", "mindset", "core_value", "identity", "money_belief", "fear", "motivation", "archetype", green falg, red fag etc).
basically extract categories which are responsible for finding the right partener.
Dont extract personal dates and person name..just traits..
Return STRICT JSON only with the following shape:
{
  "extracted_traits": [
    {"key":"...", "value":"...", "confidence": 0.0}
  ]
}
Rules:
- Confidence is a number 0.0 - 1.0.
- Return nothing else besides valid JSON.
- If there are no extracted traits, return {"extracted_traits": []}.
"""

SANA_REPLY_SYSTEM = """
You are Sana — wise, playful, caring. Speak in 1-2 short lines (max 2 sentences).
Tone: warm, slightly mysterious, trustworthy. Ask exactly one gentle follow-up question per reply.
Do NOT provide astrological predictions or timeframes unless the user explicitly asks.
Keep language natural and simple.
"""

# -------------------------
# LLM Call Wrappers
# -------------------------
def _call_chat_completions_create_model(payload):
    # Minimal wrapper for the OpenAI client style used in earlier code.
    return client.chat.completions.create(**payload)

async def call_dynamic_extractor(user_message: str) -> Dict[str, Any]:
    payload = {
        "model": "gpt-5-nano",
        "messages": [
            {"role": "system", "content": DYNAMIC_EXTRACTOR_SYSTEM},
            {"role": "user", "content": f'User message: "{user_message}"'}
        ],
    }
    resp = await to_thread_retry(_call_chat_completions_create_model, payload)
    text = resp.choices[0].message.content
    return safe_load_json_fragment(text)

async def call_sana_reply(prompt: str) -> str:
    payload = {
        "model": "gpt-5-nano",
        "messages": [
            {"role": "system", "content": SANA_REPLY_SYSTEM},
            {"role": "user", "content": prompt}
        ],
    }
    resp = await to_thread_retry(_call_chat_completions_create_model, payload)
    return resp.choices[0].message.content.strip()

# -------------------------
# Merge logic for generic psych_map
# -------------------------
def merge_into_psych_map(existing: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    existing: current psych_map (flexible dict)
    extracted: { "extracted_traits": [{"key":"...","value":"...","confidence":0.0}, ...] }
    Strategy:
      - If key is new, create entry: { "value": value, "confidence": c, "history":[{time, value, confidence}] }
      - If key exists, keep the value with higher confidence OR push to a small list for ambiguous keys.
      - Keep history for auditing.
    """
    out = json.loads(json.dumps(existing or {}))  # deep copy
    now = now_iso()
    items = extracted.get("extracted_traits") or []

    for it in items:
        key = (it.get("key") or "").strip()
        val = it.get("value")
        conf = float(it.get("confidence", 0.0))
        if not key or not val:
            continue

        # standardize key to lowercase snake (optional)
        key_slug = re.sub(r"\s+", "_", key.strip().lower())

        entry = out.get(key_slug)
        if not entry:
            out[key_slug] = {
                "value": val,
                "confidence": conf,
                "history": [{"time": now, "value": val, "confidence": conf}]
            }
            continue

        # If existing is a single value object with confidence
        try:
            existing_conf = float(entry.get("confidence", 0.0))
        except Exception:
            existing_conf = 0.0

        # Update rules:
        # - If new confidence higher by margin (>= existing_conf), replace value and append history
        # - If similar confidence and different value, store an alternatives list
        if conf >= existing_conf + 0.05:
            # replace
            entry["value"] = val
            entry["confidence"] = conf
            entry.setdefault("history", []).append({"time": now, "value": val, "confidence": conf})
        elif abs(conf - existing_conf) < 0.05 and val != entry.get("value"):
            # ambiguous: promote to alternatives
            alt_key = key_slug + "_alternatives"
            alts = out.get(alt_key, [])
            alts.append({"value": val, "confidence": conf, "time": now})
            out[alt_key] = alts[-8:]  # keep last 8 alternatives
            # still append history
            entry.setdefault("history", []).append({"time": now, "value": val, "confidence": conf})
        else:
            # lower confidence -> just append history to record evidence
            entry.setdefault("history", []).append({"time": now, "value": val, "confidence": conf})
            # Optionally nudge existing confidence slightly upward if repeated
            entry["confidence"] = max(existing_conf, conf)

        out[key_slug] = entry

    return out

# -------------------------
# Main chat endpoint
# -------------------------
@router.post("/sana/chat")
async def sana_chat(data: SanaChatMessage, background_tasks: BackgroundTasks):
    user_id = data.id
    user_name = data.name
    user_message = data.message

    if not all([user_id, user_name, user_message]):
        raise HTTPException(status_code=400, detail="Missing id, name, or message")

    # fetch user record
    resp = supabase.table("users").select(
        "id, chat_history, memories, psych_map, profile_candidates, profile_versions, chart, persona_settings, consent_flags"
    ).eq("id", user_id).single().execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="User not found")

    user = resp.data
    psych_map = user.get("psych_map") or {}
    chat_history = user.get("chat_history") or []
    memories = user.get("memories") or []
    persona_settings = user.get("persona_settings") or {}
    consent_flags = user.get("consent_flags") or {}

    now = now_iso()

    # Build a short context excerpt
    recent = chat_history[-8:]
    context_excerpt = "\n".join([f'{m.get("role","user")}: {m.get("content","")}' for m in recent])

    # build reply prompt (short, respectful of persona settings)
    ask_question = persona_settings.get("ask_question", True)
    persona_tone = persona_settings.get("tone", "playful")
    reply_prompt = f"Context:\n{context_excerpt}\nUser: {user_message}\nName: {user_name}\nTone: {persona_tone}\nKeep reply in 1-2 short lines. Ask 1 question: {ask_question}"

    # generate Sana reply (fast)
    sana_reply = await call_sana_reply(reply_prompt)

    # background: extract dynamic traits and save everything
    async def bg_save():
        try:
            # 1) append chat & memory
            new_chat = chat_history + [
                {"role": "user", "name": user_name, "content": user_message, "time": now},
                {"role": "sana", "name": "sana", "content": sana_reply, "time": now}
            ]
            new_memories = (memories or []) + [{"content": user_message, "time": now}]
            new_memories = new_memories[-400:]  # keep longer memory

            # 2) call dynamic extractor
            extractor_resp = await call_dynamic_extractor(user_message)
            # ensure shape
            extracted = extractor_resp if isinstance(extractor_resp, dict) else safe_load_json_fragment(str(extractor_resp))
            extracted_traits = extracted.get("extracted_traits", [])

            # 3) merge into psych_map
            updated_psych_map = merge_into_psych_map(psych_map, extracted)

            # 4) candidate + versions
            candidate_entry = {"candidate": extracted, "time": now}
            profile_candidates = (user.get("profile_candidates") or [])[-200:] + [candidate_entry]

            versions = (user.get("profile_versions") or [])
            versions.append({
                "before": psych_map,
                "after": updated_psych_map,
                "candidate": extracted,
                "time": now
            })
            versions = versions[-500:]

            # 5) write to Supabase
            supabase.table("users").update({
                "chat_history": new_chat,
                "memories": new_memories,
                "psych_map": updated_psych_map,
                "profile_candidates": profile_candidates,
                "profile_versions": versions
            }).eq("id", user_id).execute()

            print(f"✅ Updated psych_map for user {user_id} at {now}")
        except Exception as e:
            print("Background save error:", e)

    background_tasks.add_task(bg_save)

    # return both Sana reply and extracted traits summary (user-friendly)
    return {
        "reply": sana_reply,
        "note": "Saved to psych_map in background.",
        "extracted_preview": extracted_preview_for_client(sana_reply, user_message)
    }

# -------------------------
# Small helper to create a small preview on response (non-LLM)
# -------------------------
def extracted_preview_for_client(reply_text: str, user_message: str) -> Dict[str, Any]:
    # Lightweight local heuristic summary to show instantly (LLM extraction happens in background)
    preview = {
        "quick_hint": None,
        "suggested_follow_up": None
    }
    # Simple heuristics
    if any(w in user_message.lower() for w in ["rich", "money", "wealth", "earn", "salary"]):
        preview["quick_hint"] = {"key": "goal", "value": "financial success"}
        preview["suggested_follow_up"] = "Ask: 'What's your first small money goal right now?'"
    elif any(w in user_message.lower() for w in ["tired","burn","exhaust","drain"]):
        preview["quick_hint"] = {"key":"mood","value":"exhausted"}
        preview["suggested_follow_up"] = "Ask: 'When did this start?'"
    return preview

# attach router
app.include_router(router, prefix="")

# -------------------------
# Run notes:
# uvicorn sana_dynamic:app --reload --port 8000
# -------------------------
