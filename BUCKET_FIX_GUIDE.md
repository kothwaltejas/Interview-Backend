# 🔧 Fix Resume Upload "Bucket not found" Error

## Root Cause
The 'resumes' storage bucket is set to **PRIVATE** instead of **PUBLIC**, so the frontend can't access resume files via direct URLs.

## ✅ Solution 1: Make Bucket PUBLIC (Recommended for Development)

### Step 1: Go to Supabase Dashboard
1. Open https://app.supabase.com
2. Select your project: **InterviewAI**
3. Click **Storage** in the left sidebar

### Step 2: Edit the 'resumes' Bucket
1. Find the **'resumes'** bucket in the list
2. Click the **3 dots menu** (⋮) on the right
3. Click **Edit bucket**
4. Toggle **Public bucket** to **ON** ✅
5. Click **Save**

It should now look like:
```
🪣 resumes  [Public ✓]
```

### Step 3: Verify it Works
Run this test:
```bash
python test_supabase_storage.py
```

You should see:
```
✅ Upload successful
✅ Delete successful
```

---

## ✅ Solution 2: Use Signed URLs (More Secure)

If you don't want the bucket to be public, use signed URLs instead:

### Option A: Backend generates signed URLs

**File: `d:\InterviewAI\backend\src\database\supabase_client.py`**

Replace the `upload_resume_to_storage()` function to return a signed URL:

```python
async def upload_resume_to_storage(
    user_id: str,
    file_content: bytes,
    file_name: str
) -> str:
    """Upload resume PDF to Supabase Storage - returns SIGNED URL"""
    try:
        if not supabase:
            raise Exception("Supabase client not initialized")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = f"{user_id}/{timestamp}_{file_name}"
        
        logger.info(f"📤 Uploading resume: {file_path}")
        
        # Upload file
        response = supabase.storage.from_("resumes").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": "application/pdf"}
        )
        
        # Generate signed URL (valid for 7 days)
        signed_url = supabase.storage.from_("resumes").create_signed_url(
            file_path,
            expires_in=604800  # 7 days
        )
        
        logger.info(f"✅ Resume uploaded: {file_path}")
        logger.info(f"📎 Signed URL (7 days): {signed_url}")
        
        return signed_url
            
    except Exception as e:
        logger.error(f"❌ Error uploading resume: {e}")
        raise
```

---

## ✅ Solution 3: Create a Proxy Endpoint (Most Flexible)

Create a backend endpoint that serves the file with proper authentication:

### Add this endpoint to `src/main.py`:

```python
@app.get("/api/db/resumes/{resume_id}/download")
async def download_resume_endpoint(
    resume_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Stream resume file for authenticated user
    Protected route - user can only download own resumes
    """
    try:
        from fastapi.responses import FileResponse
        
        user_id = user["user_id"]
        
        # Get resume from database
        resume = await get_resume_by_id(resume_id)
        
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        # Verify user owns this resume
        if resume["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Extract file path from public URL
        # URL format: https://xxxxx.supabase.co/storage/v1/object/public/resumes/{user_id}/{filename}
        file_url = resume["file_url"]
        file_path = file_url.split('/resumes/', 1)[1]
        
        # Download from storage
        file_data = supabase.storage.from_("resumes").download(file_path)
        
        return FileResponse(
            file_data,
            media_type="application/pdf",
            filename=resume["file_name"]
        )
        
    except Exception as e:
        logger.error(f"Error downloading resume: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

Then update the frontend to use this endpoint instead of direct URL.

---

## 📋 Diagnosis

To find out which solution you need, run this test:

```bash
# Test 1: Check current bucket status
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))
try:
    files = supabase.storage.from_('resumes').list()
    print('✅ Bucket is accessible')
except Exception as e:
    print(f'❌ Bucket error: {e}')
"
```

---

## Recommended Fix (Step by Step)

### For Development: Use Solution 1 (Public Bucket)
1. Make the bucket PUBLIC in Supabase dashboard
2. Run `python test_supabase_storage.py` to verify  
3. You're done! ✅

### For Production: Use Solution 2 (Signed URLs)
1. Update `upload_resume_to_storage()` to return signed URLs
2. Update the database to store signed URLs instead of public URLs
3. Frontend will automatically use signed URLs

---

## Quick Test After Fix

```bash
# 1. Start backend
cd backend/src
python main.py

# 2. In another terminal, run:
cd backend
python test_supabase_storage.py

# Expected output:
# ✅ All tests passed!
# Your Supabase Storage setup is working correctly.
```

Then try uploading a resume from the frontend - it should work! ✅
