# =====================================================
# SUPABASE DATABASE SETUP GUIDE
# =====================================================

## Prerequisites

1. Supabase account (https://supabase.com)
2. Python 3.9+ installed
3. Existing InterviewAI backend

---

## STEP 1: Supabase Project Setup

### 1.1 Create Project
1. Go to https://supabase.com/dashboard
2. Click "New Project"
3. Set project name: `intervu-ai`
4. Set database password (save this!)
5. Select region closest to you
6. Click "Create new project"

### 1.2 Get API Credentials
1. Go to Project Settings > API
2. Copy these values:
   - **Project URL** (SUPABASE_URL)
   - **anon public** key (SUPABASE_ANON_KEY) - for frontend
   - **service_role** key (SUPABASE_SERVICE_KEY) - for backend
3. Go to Project Settings > API > JWT Settings
4. Copy **JWT Secret** (SUPABASE_JWT_SECRET)

---

## STEP 2: Run Database Migration

### 2.1 Execute SQL Migration
1. Open Supabase Dashboard
2. Go to **SQL Editor**
3. Create new query
4. Copy entire content from `backend/supabase_migrations/001_initial_schema.sql`
5. Paste and click **Run**
6. Verify: Go to **Table Editor** - you should see 5 tables:
   - user_profiles
   - resumes
   - interview_sessions
   - interview_answers
   - interview_statistics

### 2.2 Create Storage Bucket
1. Go to **Storage** in Supabase Dashboard
2. Click **New Bucket**
3. Name: `resumes`
4. Make it **Private** (not public)
5. Click **Create Bucket**

### 2.3 Setup Storage RLS Policies
1. Click on `resumes` bucket
2. Go to **Policies** tab
3. Create three policies:

**Policy 1: Upload**
```sql
CREATE POLICY "Users can upload own resumes"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'resumes' AND
  auth.uid()::text = (storage.foldername(name))[1]
);
```

**Policy 2: View**
```sql
CREATE POLICY "Users can view own resumes"
ON storage.objects FOR SELECT
USING (
  bucket_id = 'resumes' AND
  auth.uid()::text = (storage.foldername(name))[1]
);
```

**Policy 3: Delete**
```sql
CREATE POLICY "Users can delete own resumes"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'resumes' AND
  auth.uid()::text = (storage.foldername(name))[1]
);
```

---

## STEP 3: Update Backend Configuration

### 3.1 Update .env File
Add these to `backend/.env`:

```env
# Supabase Configuration
SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_JWT_SECRET=your-jwt-secret-key-here
```

### 3.2 Install New Dependencies
```bash
cd backend
pip install supabase python-jose[cryptography]
```

Or update `requirements.txt`:
```txt
supabase==2.3.4
python-jose[cryptography]==3.3.0
```

Then:
```bash
pip install -r requirements.txt
```

---

## STEP 4: Integrate Database Routes

### 4.1 Update main.py

Add imports at top:
```python
from src.routes.database_routes import router as db_router
```

Include router (after CORS setup):
```python
app.include_router(db_router)
```

### 4.2 Update Interview Completion Flow

Find where interview completes (when all questions answered) and add:

```python
from src.database.supabase_client import (
    insert_completed_session,
    insert_answers_bulk,
    upsert_user_statistics
)

# After interview completes
async def save_interview_to_db(session_id: str, user_id: str, resume_id: str = None):
    """Save completed interview to database"""
    
    # Get in-memory session
    session = InterviewSession.get_session(session_id)
    
    if not session:
        return
    
    # Prepare session data
    session_data = {
        "target_role": session.job_context.get("target_role"),
        "experience_level": session.job_context.get("experience_level"),
        "interview_type": session.job_context.get("interview_type"),
        "mode": "conversational",
        "total_questions": len(session.questions),
        "answered_questions": len([r for r in session.responses if not r.get("skipped")]),
        "skipped_questions": len([r for r in session.responses if r.get("skipped")]),
        "duration_seconds": int((session.end_time - session.start_time).total_seconds()),
        "topics_covered": list(set([q.get("category") for q in session.questions]))
    }
    
    # Insert session
    db_session = await insert_completed_session(user_id, resume_id, session_data)
    
    # Prepare and insert answers
    answers = []
    for idx, response in enumerate(session.responses):
        question = session.questions[idx]
        answers.append({
            "question_number": idx + 1,
            "question_text": question.get("question", ""),
            "category": question.get("category"),
            "difficulty": question.get("difficulty"),
            "answer_text": response.get("answer_text", ""),
            "is_skipped": response.get("skipped", False),
            "duration_seconds": response.get("time_taken_seconds")
        })
    
    await insert_answers_bulk(db_session["id"], answers)
    
    # Update statistics
    await upsert_user_statistics(user_id)
```

---

## STEP 5: Update Resume Upload Endpoint

Replace existing resume upload with Supabase storage:

```python
from src.database.supabase_client import upload_resume_to_storage, insert_resume
from src.auth.supabase_auth import get_current_user

@app.post("/api/resume/parse")
async def parse_resume_endpoint(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)  # Add authentication
):
    try:
        user_id = user["user_id"]
        
        # Read file
        file_content = await file.read()
        
        # Upload to Supabase Storage
        file_url = await upload_resume_to_storage(
            user_id=user_id,
            file_content=file_content,
            file_name=file.filename
        )
        
        # Parse resume
        parsed_data = parse_resume_pdf(file_content)
        
        # Save to database
        resume_record = await insert_resume(
            user_id=user_id,
            file_name=file.filename,
            file_url=file_url,
            parsed_json=parsed_data,
            file_size_bytes=len(file_content)
        )
        
        return {
            "success": True,
            "resume_id": resume_record["id"],
            "data": parsed_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## STEP 6: Frontend Integration

### 6.1 Install Supabase Client (Frontend)
```bash
cd frontend
npm install @supabase/supabase-js
```

### 6.2 Create Supabase Client
Create `frontend/src/lib/supabaseClient.ts`:

```typescript
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
```

### 6.3 Update .env.local
```env
NEXT_PUBLIC_SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 6.4 Add Auth Token to API Calls
```typescript
// Get token from Supabase auth
const { data: { session } } = await supabase.auth.getSession();
const token = session?.access_token;

// Add to API calls
fetch('http://localhost:8000/api/db/sessions', {
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});
```

---

## STEP 7: Testing

### 7.1 Test Authentication
```bash
# Should fail without token
curl http://localhost:8000/api/db/sessions

# Should succeed with token
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:8000/api/db/sessions
```

### 7.2 Test Resume Upload
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@resume.pdf" \
  http://localhost:8000/api/db/resumes/upload
```

### 7.3 Test Session Completion
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"abc123","resume_id":"xyz789"}' \
  http://localhost:8000/api/db/sessions/complete
```

### 7.4 Verify in Supabase Dashboard
1. Go to **Table Editor**
2. Check `interview_sessions` table
3. Check `interview_answers` table
4. Check `resumes` table
5. Go to **Storage** > `resumes` bucket
6. Verify PDFs are uploaded

---

## STEP 8: Enable Realtime (Optional)

If you want live updates:

```python
# Backend: Broadcast session updates
from src.database.supabase_client import SupabaseDB

client = SupabaseDB.get_client()
client.realtime.from_("interview_sessions:user_id=eq.{user_id}").on(
    "INSERT",
    lambda payload: print(f"New session: {payload}")
).subscribe()
```

---

## Common Issues & Solutions

### Issue 1: "Invalid JWT Secret"
- Make sure JWT_SECRET in .env matches Supabase JWT Secret
- Check for extra spaces or newlines

### Issue 2: "RLS Policy Error"
- Verify RLS is enabled on all tables
- Check policy conditions match your use case
- Test with service_role key (bypasses RLS) first

### Issue 3: "Storage Upload Failed"
- Verify bucket exists and is named `resumes`
- Check storage RLS policies are created
- Ensure file path format: `{user_id}/{timestamp}_{filename}`

### Issue 4: "User ID Not Found"
- Make sure Authorization header includes "Bearer " prefix
- Verify token is from Supabase auth (not custom JWT)
- Check token hasn't expired

---

## What Gets Stored

✅ **Stored in Database:**
- Completed interview sessions
- All candidate answers
- Resume files + parsed data
- Aggregate statistics
- User profiles

❌ **Not Stored:**
- In-progress sessions (use Redis later)
- Temporary conversation state
- Raw LLM prompts/responses
- follow_up_count, skip_flag (ephemeral)

---

## Next Steps

1. ✅ Run SQL migration
2. ✅ Create storage bucket
3. ✅ Update .env files
4. ✅ Install dependencies
5. ✅ Integrate auth middleware
6. ✅ Test endpoints
7. [ ] Add analytics dashboard
8. [ ] Setup Redis for in-progress sessions
9. [ ] Add email notifications (Supabase Edge Functions)
10. [ ] Deploy to production

---

## Resources

- Supabase Docs: https://supabase.com/docs
- RLS Guide: https://supabase.com/docs/guides/auth/row-level-security
- Storage Guide: https://supabase.com/docs/guides/storage
- Python Client: https://supabase.com/docs/reference/python
