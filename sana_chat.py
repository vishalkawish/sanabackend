import os
import json
import re
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, APIRouter, HTTPException
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
    raise RuntimeError("Missing OPENAI_API_KEY or SUPABASE_URL or SUPABASE_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()
router = APIRouter()

# -------------------------
# MODELS
# -------------------------
class SanaChatMessage(BaseModel):
    id: str
    name: str
    message: str

# -------------------------
# UTILITIES
# -------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def safe_load_json_fragment(text: str) -> Dict:
    if not text or not isinstance(text, str):
        return {}
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
    except Exception:
        pass
    return {}

async def to_thread(fn, *args):
    return await asyncio.to_thread(fn, *args)

# -------------------------
# SANA CHAT PROMPT
# -------------------------
SANA_REPLY_SYSTEM = """
You are Sana — warm, emotionally intelligent, and slightly expressive.
Every reply must feel natural and slightly different, even to similar messages.
Reply in 1–2 short caring lines.
Avoid repeating the same sentence structure.
No astrology. No therapy jargon.
"""


def _call_chat(payload):
    return client.chat.completions.create(**payload)

async def call_sana_reply(prompt: str) -> str:
    payload = {
        "model": "gpt-5-nano",
        "messages": [
            {"role": "system", "content": SANA_REPLY_SYSTEM},
            {"role": "user", "content": prompt}
        ]
    }
    resp = await to_thread(_call_chat, payload)
    return resp.choices[0].message.content.strip()

# -------------------------
# GPT MATCH REASONER
# -------------------------
def gpt_rank_and_explain_sync(user_profile: Dict, request_text: str, candidates: List[Dict]) -> str:
    summary = [{"id": c.get("id"), "name": c.get("name")} for c in candidates[:12]]

    system = "Return STRICT JSON: { \"matches\": [{\"id\":..., \"score\":..., \"reason\": \"...\"}] }"
    user_prompt = {
        "request_text": request_text,
        "user_profile": user_profile,
        "candidates": summary
    }

    resp = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_prompt)}
        ],
    )
    return resp.choices[0].message.content

# -------------------------
# EMBEDDINGS
# -------------------------
EMBED_MODEL = "text-embedding-3-small"

def embed_sync(text: str) -> List[float]:
    return client.embeddings.create(
        model=EMBED_MODEL,
        input=text
    ).data[0].embedding

async def embed_text_async(text: str) -> List[float]:
    return await asyncio.to_thread(embed_sync, text)

# -------------------------
# MATCHING HELPERS
# -------------------------
def normalize_gender(g: Optional[str]) -> str:
    if not g:
        return ""
    g = str(g).strip().lower()
    if g.startswith("m"): return "male"
    if g.startswith("f"): return "female"
    return ""

def try_rpc_match(query_vector: List[float], k: int = 50):
    try:
        res = supabase.rpc("match_users", {
            "query_vector": query_vector,
            "match_limit": k
        }).execute()
        return res.data or []
    except Exception as e:
        print("RPC match failed:", e)
        return []

async def vector_search_candidates(query_vector: List[float], exclude_user_id: str, k: int = 50):
    rows = try_rpc_match(query_vector, k)
    return [r for r in rows if r.get("id") != exclude_user_id]

# -------------------------
# MATCH INTENT
# -------------------------
MATCH_KEYWORDS = [
    "match", "partner", "find me", "show me", "compatible",
    "soulmate", "date", "dating", "true love", "loyal", "someone who"
]

def looks_like_match_request(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in MATCH_KEYWORDS)

# =========================================================
# ✅ ✅ ✅ FINAL /sana/chat ENDPOINT (ONE PIECE)
# =========================================================
@router.post("/sana/chat")
async def sana_chat(data: SanaChatMessage):
    user_id = data.id
    user_name = data.name
    user_message = data.message

    if not all([user_id, user_name, user_message]):
        raise HTTPException(status_code=400, detail="Missing id, name, or message")

    user = supabase.table("users").select(
        "chat_history, psych_map, profile_candidates, gender, memories"
    ).eq("id", user_id).single().execute().data

    chat_history = user.get("chat_history") or []
    memories = user.get("memories") or []
    psych_map = user.get("psych_map") or {}

    now = now_iso()
    is_match_request = looks_like_match_request(user_message)

    # ==================================================
    # ❤️ MATCH MODE — PLACEHOLDER + VECTOR + GPT
    # ==================================================
    if is_match_request:
        try:
            sana_reply = "Sana found these for you."

            # VECTOR SEARCH
            request_vector = await embed_text_async(user_message)
            candidates = await vector_search_candidates(
                request_vector,
                exclude_user_id=user_id,
                k=50
            )

            # GENDER FILTER
            user_gender = normalize_gender(user.get("gender"))
            if user_gender in ["male", "female"]:
                target_gender = "female" if user_gender == "male" else "male"
                candidates = [
                    c for c in candidates
                    if normalize_gender(c.get("gender")) == target_gender
                ]

            top_for_refine = candidates[:15]

            # GPT REASONING
            def _gpt_refine():
                return gpt_rank_and_explain_sync(
                    psych_map,
                    user_message,
                    top_for_refine
                )

            gpt_resp_text = await asyncio.to_thread(_gpt_refine)
            matches_struct = safe_load_json_fragment(gpt_resp_text)

            if isinstance(matches_struct, dict):
                match_results = matches_struct.get("matches")
            else:
                match_results = None

            # FALLBACK
            if not match_results:
                match_results = [
                    {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "score": None,
                        "reason": "High emotional similarity (vector match)."
                    }
                    for c in top_for_refine[:5]
                ]

            # SAVE MATCH HISTORY
            profile_candidates = (user.get("profile_candidates") or [])[-200:]
            profile_candidates.append({
                "match_results": match_results,
                "time": now
            })

            supabase.table("users").update({
                "profile_candidates": profile_candidates
            }).eq("id", user_id).execute()

            return {
                "reply": sana_reply,
                "match_results": match_results
            }

        except Exception as e:
            print("MATCH ERROR:", e)
            return {
                "reply": "Matching failed. Try again.",
                "match_results": []
            }

    # ==================================================
    # 💬 NORMAL CHAT MODE
    # ==================================================
    else:
        recent = chat_history[-6:]
        context = "\n".join([m.get("content", "") for m in recent])

        reply_prompt = f"Context:\n{context}\nUser: {user_message}\nName: {user_name}"

        try:
            sana_reply = await call_sana_reply(reply_prompt)
        except Exception as e:
            print("Chat error:", e)
            sana_reply = "I’m here with you."

        chat_history += [
            {"role": "user", "name": user_name, "content": user_message, "time": now},
            {"role": "sana", "name": "sana", "content": sana_reply, "time": now}
        ]

        memories.append({"content": user_message, "time": now})

        supabase.table("users").update({
            "chat_history": chat_history[-200:],
            "memories": memories[-400:]
        }).eq("id", user_id).execute()

        return {
            "reply": sana_reply,
            "match_results": None
        }

# -------------------------
# ATTACH ROUTER
# -------------------------

# -------------------------
# RUN
# -------------------------
# uvicorn sana_dynamic:app --reload --port 8000
