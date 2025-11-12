from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, UploadFile, Form, HTTPException
from supabase import create_client
import os, mimetypes

router = APIRouter()

# -------------------------
# Supabase setup (use SERVICE ROLE key)
# -------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # <-- make sure this is service role key
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

BUCKET = "profile-pics"

# -------------------------
# Debug helper
# -------------------------
def debug(msg, data=None):
    if data is not None:
        print(f"🔹 DEBUG: {msg} -> {data}")
    else:
        print(f"🔹 DEBUG: {msg}")

# -------------------------
# Ensure bucket exists
# -------------------------
def ensure_bucket_exists():
    try:
        buckets = supabase.storage.list_buckets()
        bucket_names = [b['name'] for b in buckets]
        debug("Existing buckets", bucket_names)

        if BUCKET not in bucket_names:
            debug("Creating bucket", BUCKET)
            supabase.storage.create_bucket(BUCKET, {"public": True})
            debug("✅ Created bucket", BUCKET)
        else:
            debug("✅ Bucket exists", BUCKET)
    except Exception as e:
        debug("⚠ Bucket check failed", str(e))

# -------------------------
# Upload endpoint
# -------------------------
@router.post("/uploadProfileImage")
async def upload_profile_image(
    userId: str = Form(...),
    file: UploadFile = Form(...)
):
    try:
        debug("Received upload request", {"userId": userId, "filename": file.filename})
        ensure_bucket_exists()

        content = await file.read()
        debug("File size bytes", len(content))

        # Get file extension
        ext = os.path.splitext(file.filename)[1] or ".png"
        filename = f"profile_{userId}{ext}"
        debug("Uploading as filename", filename)

        # Guess content type
        content_type, _ = mimetypes.guess_type(file.filename)
        if content_type is None:
            content_type = "application/octet-stream"
        debug("Detected content type", content_type)

        # Upload to Supabase (use upsert="true" as string)
        supabase.storage.from_(BUCKET).upload(
            filename,
            content,
            {"upsert": "true"}  # <- must be string
        )
        debug("Upload successful", filename)

        # Get public URL
        public_url = supabase.storage.from_(BUCKET).get_public_url(filename)
        debug("Public URL", public_url)

        # Update user table
        res = supabase.table("users").update({"profilePicUrl": public_url}).eq("id", userId).execute()
        debug("DB update result", res)

        return {"url": public_url}

    except Exception as e:
        debug("Upload failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))
