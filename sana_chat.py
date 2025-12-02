# sana_dynamic.py
import os
import json
import re
import asyncio
import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

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
DATABASE_URL = os.environ.get("DATABASE_URL")  # optional if you use psycopg2 fallback

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
# LLM Prompts (dynamic extractor + reply)
# -------------------------
DYNAMIC_EXTRACTOR_SYSTEM = """
You are a psychological inference engine for building meaningfull connection with people. You're an AI called Sana.
Your job is to extract HUMAN relationship traits from the user’s message and map them into a FIXED STRUCTURE. 
Only extract TRAITS which are helpful to build a psychological profile for matchmaking and relationship.
relationship traits include: values, attachment style, personality traits, love languages, emotional behaviors, conflict styles, fears, and other relevant psychological characteristics...Red Flags and Green Flags are so important.
You may CREATE NEW TRAIT CATEGORIES automatically when useful (like "dealbreakers", "partner_preferences", "emotional_behaviors", "conflict_style", "how_they_behave_when_stressed, sad, emotional etc", green_flag, red_flag etc).
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

LIGHT_EXTRACTOR_SYSTEM = """
Extract ONLY these 28 fields from the user's latest message:

{
  "moods": [],
  "personality_traits": [],
  "love_language": [],
  "relationship_goals": [],
  "interests": [],
  "red_flags": [],
  "green_flags": [],
  "attachment_style": [],
  "communication_style": [],
  "conflict_style": [],
  "emotional_triggers": [],
  "stress_behaviors": [],
  "trauma_signals": [],
  "boundaries": [],
  "dealbreakers": [],
  "partner_preferences": [],
  "affection_style": [],
  "trust_style": [],
  "intimacy_style": [],
  "lifestyle_preferences": [],
  "values": [],
  "core_fears": [],
  "stability_needs": [],
  "compatibility_requirements": [],
  "likes": [],
  "dislikes": [],
  "emotional_needs": [],
  "emotional_giving_style": []
}

Rules:
- Only pull what is clearly present in the message.
- If not visible, return an empty array.
- Keep values short (1–3 words).
- Relationship-relevant only.
- STRICT JSON only.
"""



SANA_REPLY_SYSTEM = """
You are Sana — a warm, wise, slightly mysterious relationship guide.
Your purpose is to help the user understand their emotional patterns, improve their relationship behaviors, 
heal through difficult moments, and move closer to finding the right partner.

Speak in 1–2 short sentences only.
Tone: caring, calm, insightful, emotionally safe. 
Offer small helpful reflections about the user's patterns, feelings, or relationships.
Give gentle encouragement when the user is going through breakups, confusion, loneliness, or emotional ups and downs.

Do NOT provide astrological predictions or timeframes unless the user explicitly asks.
Keep language simple, human, and comforting. Avoid therapy jargon or long explanations.
"""


async def call_light_extractor(user_message: str) -> Dict[str, Any]:
    payload = {
        "model": "gpt-5-nano",
        "messages": [
            {"role": "system", "content": LIGHT_EXTRACTOR_SYSTEM},
            {"role": "user", "content": user_message}
        ],
    }
    resp = await to_thread_retry(_call_chat_completions_create_model, payload)
    text = resp.choices[0].message.content
    try:
        return json.loads(text)
    except:
        return {
            "moods": [],
            "personality_traits": [],
            "love_language": [],
            "relationship_goals": [],
            "interests": [],
            "red_flags": [],
            "green_flags": []
        }



def merge_list_field(existing, new_values):
    if not isinstance(existing, list):
        existing = []
    for item in new_values:
        if item not in existing:
            existing.append(item)
    return existing


# -------------------------
# LLM Call Wrappers
# -------------------------
def _call_chat_completions_create_model(payload):
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

# small helper to call GPT for ranking/refinement (single call)
def gpt_rank_and_explain_sync(user_profile: Dict, request_text: str, candidates: List[Dict]) -> str:
    # build pruned payload
    candidate_summaries = []
    for c in candidates:
        pm = c.get("psych_map") or {}
        summary = {
            "id": c.get("id"),
            "name": c.get("name"),
        }
        candidate_summaries.append(summary)

    system = (
        "You are Sana: a relationship psychologist and matchmaker. "
        "Given the requesting user's profile and their natural-language request, rank the candidates by suitability "
        "and return STRICT JSON with top 5 entries in the shape: {\"matches\": [{\"id\":..., \"score\":..., \"reason\": \"...\"}] }."
    )
    user_prompt = {
        "request_text": request_text,
        "user_profile": user_profile,
        "candidates": candidate_summaries,
        "instructions": "Rank and explain briefly. Return JSON only."
    }
    resp = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role":"system","content":system},
            {"role":"user","content": json.dumps(user_prompt, ensure_ascii=False)}
        ],
        temperature=1,
    )
    return resp.choices[0].message.content

# -------------------------
# Embedding helpers (embed text and embed psych_map)
# -------------------------
EMBED_MODEL = "text-embedding-3-small"  # 1536 dims

def embed_sync(text: str) -> List[float]:
    # minimal sync wrapper for the OpenAI client
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding

async def embed_text_async(text: str) -> List[float]:
    return await asyncio.to_thread(embed_sync, text)

def psych_map_to_plaintext(pm: Dict[str, Any]) -> str:
    # Stable textual serialization designed to capture key fields compactly for embeddings
    if not pm:
        return ""
    parts = []
    # Order keys deterministically
    for k in sorted(pm.keys()):
        v = pm[k]
        if isinstance(v, dict) and "value" in v:
            parts.append(f"{k}: {v.get('value')}")
        else:
            parts.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    return ". ".join(parts)

async def embed_and_store_user_vector(user_id: str, psych_map: Dict[str, Any]):
    try:
        text = psych_map_to_plaintext(psych_map)
        if not text:
            return
        vector = await embed_text_async(text)
        # update supabase
        supabase.table("users").update({
            "psych_map": psych_map,
            "psych_vector": vector
        }).eq("id", user_id).execute()
        print(f"✅ Embedded and stored vector for {user_id}")
    except Exception as e:
        print("embed_and_store_user_vector error:", e)

# -------------------------
# Matching helpers (RPC first, fallback local)
# -------------------------
def try_rpc_match(query_vector: List[float], k: int = 200):
    """
    Tries to call a Postgres RPC `match_users` that returns nearest users.
    The DB function must be created in Postgres (see instructions beforehand).
    """
    try:
        # supabase.rpc expects params as python types; if DB function expects vector, libs differ.
        # This assumes you created a function like earlier: match_users(query_vector vector, match_limit int)
        res = supabase.rpc("match_users", {"query_vector": query_vector, "match_limit": k}).execute()
        return res.data or []
    except Exception as e:
        # rpc not available or failed
        print("RPC match_users failed or not available:", e)
        return None

def cosine_similarity(a: List[float], b: List[float]) -> float:
    # basic safe cosine, returns -1..1
    if not a or not b:
        return -1.0
    # same len expected
    if len(a) != len(b):
        # if lengths mismatch, try trim to min
        m = min(len(a), len(b))
        a = a[:m]
        b = b[:m]
    dot = sum(x*y for x,y in zip(a,b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)

def local_vector_match(all_users: List[Dict], query_vector: List[float], k: int = 200) -> List[Dict]:
    scored = []
    for u in all_users:
        vec = u.get("psych_vector")
        if not vec:
            continue
        try:
            sim = cosine_similarity(query_vector, vec)
        except Exception:
            sim = -1.0
        scored.append({"user": u, "score": sim})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return [s["user"] for s in scored[:k]]

async def vector_search_candidates(request_vector: List[float], exclude_user_id: Optional[str], k: int = 200) -> List[Dict]:
    # 1) try RPC fast path
    rpc_res = try_rpc_match(request_vector, k)
    if rpc_res is not None:
        # rpc returned rows; filter out requesting user
        results = [r for r in rpc_res if r.get("id") != exclude_user_id]
        return results[:k]

    # 2) fallback: pull users with non-null psych_vector (small DB/testing)
    try:
        res = supabase.table("users").select("id, name, psych_map, psych_vector").execute()
        rows = res.data or []
        # filter out requester
        rows = [r for r in rows if r.get("id") != exclude_user_id]
        candidates = await asyncio.to_thread(local_vector_match, rows, request_vector, k)
        return candidates
    except Exception as e:
        print("vector_search_candidates fallback failed:", e)
        return []

# -------------------------
# Intent detection (simple)
# -------------------------
MATCH_KEYWORDS = [
    "match", "partner", "find me", "show me", "compatible", "soulmate", "mate", "date", "dating",
    "true love", "loyal", "loyal partner", "bring me coffee", "coffee", "someone who", "looking for"
]

def looks_like_match_request(text: str) -> bool:
    t = text.lower()
    # simple heuristics: keywords or phrases that imply matchmaking
    for kw in MATCH_KEYWORDS:
        if kw in t:
            return True
    # also short form: "I want someone who ..." pattern
    if re.search(r"\bi want (someone|a)\b", t):
        return True
    return False

# -------------------------
# Merge logic (kept same)
# -------------------------
def merge_into_psych_map(existing: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
    out = json.loads(json.dumps(existing or {}))  # deep copy
    now = now_iso()
    items = extracted.get("extracted_traits") or []

    for it in items:
        key = (it.get("key") or "").strip()
        val = it.get("value")
        conf = float(it.get("confidence", 0.0))
        if not key or val is None or val == "":
            continue

        key_slug = re.sub(r"\s+", "_", key.strip().lower())

        entry = out.get(key_slug)
        if not entry:
            out[key_slug] = {
                "value": val,
                "confidence": conf,
                "history": [{"time": now, "value": val, "confidence": conf}]
            }
            continue

        try:
            existing_conf = float(entry.get("confidence", 0.0))
        except Exception:
            existing_conf = 0.0

        if conf >= existing_conf + 0.05:
            entry["value"] = val
            entry["confidence"] = conf
            entry.setdefault("history", []).append({"time": now, "value": val, "confidence": conf})
        elif abs(conf - existing_conf) < 0.05 and val != entry.get("value"):
            alt_key = key_slug + "_alternatives"
            alts = out.get(alt_key, [])
            alts.append({"value": val, "confidence": conf, "time": now})
            out[alt_key] = alts[-8:]
            entry.setdefault("history", []).append({"time": now, "value": val, "confidence": conf})
        else:
            entry.setdefault("history", []).append({"time": now, "value": val, "confidence": conf})
            entry["confidence"] = max(existing_conf, conf)

        out[key_slug] = entry

    return out

# -------------------------
# Small helper to create a small preview on response (non-LLM)
# -------------------------
def extracted_preview_for_client(reply_text: str, user_message: str) -> Dict[str, Any]:
    preview = {
        "quick_hint": None,
        "suggested_follow_up": None
    }
    if any(w in user_message.lower() for w in ["rich", "money", "wealth", "earn", "salary"]):
        preview["quick_hint"] = {"key": "goal", "value": "financial success"}
        preview["suggested_follow_up"] = "Ask: 'What's your first small money goal right now?'"
    elif any(w in user_message.lower() for w in ["tired","burn","exhaust","drain"]):
        preview["quick_hint"] = {"key":"mood","value":"exhausted"}
        preview["suggested_follow_up"] = "Ask: 'When did this start?'"
    return preview

# -------------------------
# Main chat endpoint (upgraded, includes matching)
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
       """
       id,
       chat_history,
       psych_map,
       profile_candidates,
       profile_versions,
       chart,
       persona_settings,
       relationship_profile
    """
    ).eq("id", user_id).single().execute()


    if not resp.data:
        raise HTTPException(status_code=404, detail="User not found")

    user = resp.data
    psych_map = user.get("psych_map") or {}
    chat_history = user.get("chat_history") or []
    memories = user.get("memories") or []
    persona_settings = user.get("persona_settings") or {}

    now = now_iso()

    # Build a short context excerpt
    recent = chat_history[-8:]
    context_excerpt = "\n".join([f'{m.get("role","user")}: {m.get("content","")}' for m in recent])

    # decide if the message is a match request (simple)
    is_match_request = looks_like_match_request(user_message)

    # build reply prompt (short, respectful of persona settings)
    ask_question = persona_settings.get("ask_question", True)
    persona_tone = persona_settings.get("tone", "playful")
    reply_prompt = f"Context:\n{context_excerpt}\nUser: {user_message}\nName: {user_name}\nTone: {persona_tone}\nKeep reply in 1-2 short lines. Ask 1 question: {ask_question}"

    # If this is a match request, we will run matching pipeline and include results.
    match_results = None
    sana_reply = None

    if is_match_request:
        # quick, friendly immediate reply to user (Sana voice)
        sana_reply = await call_sana_reply(reply_prompt + "\n(Short reply while I search for matches.)")

        # run matching pipeline: embed request -> vector search -> GPT refine
        try:
            request_text = user_message
            request_vector = await embed_text_async(request_text)

            # get top candidates (rpc or fallback)
            candidates = await vector_search_candidates(request_vector, exclude_user_id=user_id, k=200)
            # -------------------------
            # Gender filtering (simple opposite-gender logic)
            # -------------------------
            user_gender = (user.get("gender") or "").lower()

            if user_gender in ["male", "female"]:
               target_gender = "female" if user_gender == "male" else "male"

               # Filter candidates by opposite gender
               filtered = []
               for c in candidates:
                    c_gender = (c.get("gender") or "").lower()
                    if c_gender == target_gender:
                       filtered.append(c)
               candidates = filtered


            # refine top N with GPT (send top 20)
            top_for_refine = candidates[:20]
            # call GPT to rank and explain (sync wrapper in thread)
            def _gpt_refine():
                return gpt_rank_and_explain_sync(psych_map, request_text, top_for_refine)

            gpt_resp_text = await asyncio.to_thread(_gpt_refine)
            # Parse GPT output safely
            matches_struct = safe_load_json_fragment(gpt_resp_text)
            match_results = matches_struct.get("matches") if isinstance(matches_struct, dict) else None

            # If GPT returned nothing, create a fallback simple list
            if not match_results:
                # produce fallback top 5 from candidates with simple scores (if vector search succeeded)
                fallback = []
                for c in top_for_refine[:5]:
                    fallback.append({
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "score": None,
                        "reason": "Close in semantic space to your request (fast fallback)."
                    })
                match_results = fallback

        except Exception as e:
            print("Matching pipeline error:", e)
            match_results = None

    else:
        # normal conversational reply (no matching)
        sana_reply = await call_sana_reply(reply_prompt)

    # background: extract dynamic traits and save everything (and embed vector)
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
            # NEW: extract lightweight personality fields
            light = await call_light_extractor(user_message)

            extracted = extractor_resp if isinstance(extractor_resp, dict) else safe_load_json_fragment(str(extractor_resp))

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

            relationship_profile = user.get("relationship_profile") or {}

            # Merge 28 lightweight traits
            for key in RELATIONSHIP_KEYS:
                existing_list = relationship_profile.get(key, [])
                new_list = light.get(key, [])

                if not isinstance(existing_list, list):
                   existing_list = []

                merged = merge_list_field(existing_list, new_list)
                relationship_profile[key] = merged



            # 5) write to Supabase
            supabase.table("users").update({
                "chat_history": new_chat,
                "memories": new_memories,
                "psych_map": updated_psych_map,
                "profile_candidates": profile_candidates,
                "profile_versions": versions,
                "relationship_profile": relationship_profile
            }).eq("id", user_id).execute()

            # 6) create & store embedding vector for updated psych_map (async)
            # We run the embedding store in a separate thread so background task doesn't block
            await embed_and_store_user_vector(user_id, updated_psych_map)

            print(f"✅ Updated psych_map + vector for user {user_id} at {now}")
        except Exception as e:
            print("Background save error:", e)

    background_tasks.add_task(bg_save)

    # build return object: include Sana's reply + match_results if any + small preview
    response = {
        "reply": sana_reply,
        "extracted_preview": extracted_preview_for_client(sana_reply, user_message),
        "match_results": match_results,
        "note": "Saved to psych_map and (re-)embedded in background."
    }
    return response

# attach router
app.include_router(router, prefix="")

# -------------------------
# Run notes & DB helper SQL (one time migration)
# -------------------------
"""
If you haven't created the psych_vector col / pgvector extension yet, run this (Supabase SQL):

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS psych_vector vector(1536);

-- optional ivfflat index:
CREATE INDEX IF NOT EXISTS users_psych_vector_idx
  ON public.users USING ivfflat (psych_vector vector_l2_ops) WITH (lists = 100);

Also (optional) add a helper RPC for fastest matches:
CREATE OR REPLACE FUNCTION match_users(query_vector vector(1536), match_limit int)
RETURNS TABLE (id uuid, name text, psych_map jsonb, psych_vector vector, similarity float)
LANGUAGE sql STABLE AS $$
  SELECT id, name, psych_map, psych_vector, 1 - (psych_vector <=> query_vector) AS similarity
  FROM users
  WHERE psych_vector IS NOT NULL
  ORDER BY psych_vector <=> query_vector
  LIMIT match_limit;
$$;
"""
# -------------------------
# uvicorn sana_dynamic:app --reload --port 8000
# -------------------------
