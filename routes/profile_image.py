from fastapi import APIRouter, UploadFile, Form, HTTPException
from supabase import create_client
import os, mimetypes
from urllib.parse import urlparse
import asyncio

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET = "profile-pics"

@router.post("/uploadProfileImage")
async def upload_profile_image(userId: str = Form(...), file: UploadFile = Form(...)):
    try:
        # 1️⃣ Read file content
        content = await file.read()

        # 2️⃣ Detect extension and content type
        ext = os.path.splitext(file.filename)[1] or ".png"
        content_type, _ = mimetypes.guess_type(file.filename)
        if not content_type:
            content_type = "image/png"

        filename = f"profile_{userId}{ext}"

        # 3️⃣ Delete old profile pic if exists
        user = supabase.table("users").select("profile_pic_url").eq("id", userId).single().execute()
        old_url = user.data.get("profile_pic_url") if user.data else None
        if old_url:
            old_filename = os.path.basename(urlparse(old_url).path)
            try:
                supabase.storage.from_(BUCKET).remove([old_filename])
                print(f"✅ Deleted old profile image: {old_filename}")
            except Exception as e:
                print(f"⚠ Failed to delete old profile image: {e}")

        # 4️⃣ Upload new file
        supabase.storage.from_(BUCKET).upload(
            filename,
            content,
            {"content-type": content_type, "upsert": True}
        )

        # 5️⃣ Get public URL
        public_url = supabase.storage.from_(BUCKET).get_public_url(filename)
        url = public_url.get("publicUrl") if isinstance(public_url, dict) else public_url

        # 6️⃣ Update users table
        supabase.table("users").update({"profile_pic_url": url}).eq("id", userId).execute()

        return {"url": url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
