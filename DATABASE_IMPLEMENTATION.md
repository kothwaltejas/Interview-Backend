# Supabase Database Implementation - Quick Reference

## 📋 What We Created

### 1. **Database Schema** (`supabase_migrations/001_initial_schema.sql`)
- 5 tables with RLS policies
- Indexes for performance
- Views for complex queries
- Storage bucket configuration

### 2. **Python Database Client** (`src/database/supabase_client.py`)
- Complete CRUD operations
- Resume management
- Session persistence
- Statistics aggregation
- Storage operations

### 3. **Authentication Middleware** (`src/auth/supabase_auth.py`)
- JWT token validation
- User ID extraction
- FastAPI dependencies

### 4. **API Routes** (`src/routes/database_routes.py`)
- Protected endpoints
- Complete examples
- Integration patterns

---

## 🚀 Quick Start Integration

### Add to `main.py`:

```python
# Add imports
from src.routes.database_routes import router as db_router
from src.auth.supabase_auth import get_current_user
from src.database.supabase_client import (
    insert_completed_session,
    insert_answers_bulk,
    upsert_user_statistics
)

# Include router
app.include_router(db_router)

# Example: Save interview on completion
@app.get("/api/session/{session_id}/summary")
async def get_session_summary_endpoint(
    session_id: str,
    user: dict = Depends(get_current_user)  # Add auth
):
    user_id = user["user_id"]
    
    session = InterviewSession.get_session(session_id)
    
    # ... existing summary logic ...
    
    # NEW: Save to database
    await save_session_to_db(session, user_id)
    
    return summary

async def save_session_to_db(session, user_id: str):
    """Helper to save completed session"""
    
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
    db_session = await insert_completed_session(user_id, None, session_data)
    
    # Insert answers
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
    await upsert_user_statistics(user_id)
```

---

## 🔐 Authentication Usage

### Protect Any Route:
```python
from fastapi import Depends
from src.auth.supabase_auth import get_current_user

@app.post("/api/protected-route")
async def protected_route(
    request: YourRequest,
    user: dict = Depends(get_current_user)
):
    user_id = user["user_id"]
    email = user["email"]
    
    # Your logic using user_id
    return {"message": f"Hello {email}"}
```

### Optional Auth:
```python
from src.auth.supabase_auth import get_optional_user

@app.get("/api/public-route")
async def public_route(user: Optional[dict] = Depends(get_optional_user)):
    if user:
        # Personalized response
        return await get_user_data(user["user_id"])
    else:
        # Public response
        return get_public_data()
```

---

## 📊 Database Operations

### Resume Upload:
```python
from src.database.supabase_client import upload_resume_to_storage, insert_resume

file_url = await upload_resume_to_storage(user_id, file_content, filename)
resume = await insert_resume(user_id, filename, file_url, parsed_json)
```

### Save Session:
```python
session_data = {
    "target_role": "Full Stack Developer",
    "experience_level": "3-5 years",
    "interview_type": "Technical",
    "mode": "conversational",
    "total_questions": 10,
    "answered_questions": 8,
    "skipped_questions": 2,
    "duration_seconds": 1200
}

db_session = await insert_completed_session(user_id, resume_id, session_data)
```

### Save Answers:
```python
answers = [
    {
        "question_number": 1,
        "question_text": "Tell me about yourself",
        "category": "introduction",
        "difficulty": "easy",
        "answer_text": "I'm a full stack developer...",
        "is_skipped": False,
        "duration_seconds": 90
    }
    # ... more answers
]

await insert_answers_bulk(db_session["id"], answers)
```

### Get User Data:
```python
# Get sessions
sessions = await get_user_sessions(user_id, limit=20)

# Get statistics
stats = await get_user_statistics(user_id)

# Get resumes
resumes = await get_user_resumes(user_id)
```

---

## 🗄️ Database Schema Overview

```
user_profiles
├─ id (PK, FK to auth.users)
├─ full_name
├─ email
└─ avatar_url

resumes
├─ id (PK)
├─ user_id (FK)
├─ file_url
├─ parsed_json (JSONB)
└─ skills (array)

interview_sessions
├─ id (PK)
├─ user_id (FK)
├─ resume_id (FK)
├─ target_role
├─ experience_level
├─ interview_type
├─ mode
├─ total_questions
├─ average_score
└─ performance_tier

interview_answers
├─ id (PK)
├─ session_id (FK)
├─ question_number
├─ question_text
├─ category
├─ answer_text
├─ is_skipped
└─ score

interview_statistics
├─ user_id (PK, FK)
├─ total_interviews
├─ total_questions_answered
├─ average_overall_score
└─ most_common_role
```

---

## 🔄 Data Flow

### Interview Lifecycle:

1. **Resume Upload** → `resumes` table + Supabase Storage
2. **Start Interview** → In-memory session (NOT in DB)
3. **Answer Questions** → In-memory only
4. **Complete Interview** → Save to `interview_sessions` + `interview_answers`
5. **Update Stats** → `interview_statistics` table

### Why This Design?

✅ **In-memory during interview:**
- Fast performance
- No DB overhead per question
- Better user experience

✅ **Persist after completion:**
- Permanent record
- Analytics data
- Historical tracking

---

## 🛡️ Security Features

### Row Level Security (RLS)
- Users can only access their own data
- Enforced at database level
- Cannot be bypassed by API

### JWT Authentication
- Supabase handles auth
- Tokens contain user_id
- Backend validates every request

### Storage Security
- Private buckets
- User-specific folders
- RLS on file access

---

## 📈 Analytics Ready

All queries optimized with indexes:
- User sessions by date
- Performance tracking
- Topic analysis
- Score aggregation

Example analytics query:
```python
# Get average scores by role
client = SupabaseDB.get_client()
result = client.table("interview_sessions")\
    .select("target_role, avg(average_score)")\
    .group_by("target_role")\
    .execute()
```

---

## 🎯 Next Steps

1. ✅ Run migration in Supabase
2. ✅ Update .env files
3. ✅ Install dependencies
4. ✅ Add auth to existing endpoints
5. ✅ Test with Postman/Thunder Client
6. [ ] Build dashboard UI
7. [ ] Add Redis for sessions
8. [ ] Deploy to production

---

## 📞 New API Endpoints Available

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/db/resumes/upload` | POST | ✅ | Upload resume |
| `/api/db/resumes` | GET | ✅ | Get user resumes |
| `/api/db/sessions/complete` | POST | ✅ | Save session |
| `/api/db/sessions` | GET | ✅ | Get sessions |
| `/api/db/sessions/{id}` | GET | ✅ | Get session detail |
| `/api/db/statistics` | GET | ✅ | Get user stats |
| `/api/db/dashboard` | GET | ✅ | Complete dashboard |

---

## 💡 Pro Tips

1. **Always extract user_id from JWT** - Never trust frontend
2. **Use bulk inserts** for answers - Much faster
3. **Update statistics async** - Don't block response
4. **Cache frequently accessed data** - Add Redis later
5. **Monitor query performance** - Use Supabase dashboard

---

## 🐛 Debugging

### Check if RLS is working:
```python
# This should only return user's own data
sessions = await get_user_sessions(user_id)
```

### Test without auth:
```python
# Use service_role key (bypasses RLS)
client = SupabaseDB.get_client()  # Uses SUPABASE_SERVICE_KEY
```

### View SQL queries:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
# Will show all Supabase queries
```

---

## ✨ Complete Migration Completed!

Your InterviewAI platform now has:
- ✅ Persistent database storage
- ✅ Secure authentication
- ✅ User data isolation
- ✅ Analytics ready
- ✅ Production ready architecture

Happy coding! 🚀
