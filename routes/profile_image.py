from dotenv import load_dotenv
load_dotenv()
from fastapi import APIRouter, UploadFile, Form, HTTPException
from supabase import create_client
import os, mimetypes

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET = "profile-pics"

def ensure_bucket_exists():
    try:
        buckets = supabase.storage.list_buckets()
        bucket_names = [b['name'] for b in buckets]

        if BUCKET not in bucket_names:
            supabase.storage.create_bucket(
                BUCKET,
                {"public": True}
            )
            print(f"✅ Created bucket: {BUCKET}")
        else:
            print(f"✅ Bucket exists: {BUCKET}")
    except Exception as e:
        print("⚠ Bucket check failed:", e)



@router.post("/uploadProfileImage")
async def upload_profile_image(userId: str = Form(...), file: UploadFile = Form(...)):
    try:
        ensure_bucket_exists()

        content = await file.read()

        # Get original extension
        ext = os.path.splitext(file.filename)[1] or ".png"
        filename = f"profile_{userId}{ext}"

        # Detect content type
        content_type, _ = mimetypes.guess_type(file.filename)
        if content_type is None:
            content_type = "image/png"

        # Upload file to bucket (overwrite if exists)
        supabase.storage.from_(BUCKET).upload(
            filename,
            content,
            {"content-type": content_type, "upsert": "true"}
        )

        # Get public URL
        public_url = supabase.storage.from_(BUCKET).get_public_url(filename)

        # Update in users table
        supabase.table("users").update({"profile_pic_url": public_url}).eq("id", userId).execute()

        return {"url": public_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
