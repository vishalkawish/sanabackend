from dotenv import load_dotenv
load_dotenv()
from fastapi import APIRouter, UploadFile, Form, HTTPException
from supabase import create_client
import os, mimetypes

router = APIRouter()

# -------------------
# Supabase setup
# -------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET = "profile-pics"

# -------------------
# Ensure bucket exists
# -------------------
def ensure_bucket_exists():
    try:
        buckets = supabase.storage.list_buckets()
        bucket_names = [b['name'] for b in buckets]
        if BUCKET not in bucket_names:
            supabase.storage.create_bucket(BUCKET, {"public": True})
            print(f"✅ Created bucket: {BUCKET}")
        else:
            print(f"✅ Bucket exists: {BUCKET}")
    except Exception as e:
        print("⚠ Bucket check failed:", e)

# -------------------
# Upload Profile Image
# -------------------
@router.post("/uploadProfileImage")
async def upload_profile_image(userId: str = Form(...), file: UploadFile = Form(...)):
    try:
        ensure_bucket_exists()

        # Read content
        content = await file.read()

        # Preserve extension
        ext = os.path.splitext(file.filename)[1] or ".png"
        filename = f"profile_{userId}{ext}"

        # Detect MIME type
        content_type, _ = mimetypes.guess_type(file.filename)
        if not content_type:
            content_type = "image/png"

        # Delete old profile pic if exists
        user_resp = supabase.table("users").select("profile_pic_url").eq("id", userId).single().execute()
        old_url = user_resp.data.get("profile_pic_url") if user_resp.data else None
        if old_url:
            try:
                old_filename = old_url.split("/")[-1]
                supabase.storage.from_(BUCKET).remove([old_filename])
                print(f"✅ Deleted old profile image: {old_filename}")
            except Exception as e:
                print(f"⚠ Failed to delete old image: {e}")

        # Upload new image
        supabase.storage.from_(BUCKET).upload(
            filename,
            content,
            {"content-type": content_type, "upsert": True}
        )

        # Get public URL
        public_url = supabase.storage.from_(BUCKET).get_public_url(filename)

        # Update user table
        supabase.table("users").update({"profile_pic_url": public_url}).eq("id", userId).execute()

        return {"url": public_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
