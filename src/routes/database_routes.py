"""
Example FastAPI routes using Supabase Database + Auth
Demonstrates how to integrate authentication and database operations
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import Optional, List
from pydantic import BaseModel
import logging

from auth.supabase_auth import get_current_user
from database.supabase_client import (
    insert_resume,
    get_user_resumes,
    get_resume_by_id,
    insert_completed_session,
    insert_answers_bulk,
    get_user_sessions,
    get_session_by_id,
    get_session_answers,
    upsert_user_statistics,
    get_user_statistics,
    upload_resume_to_storage,
    upsert_user_profile,
    get_user_profile,
    _db_delete,
    delete_resume_from_storage
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/db", tags=["database"])


# =====================================================
# REQUEST MODELS
# =====================================================

class CompleteSessionRequest(BaseModel):
    """Request to save completed interview session"""
    session_id: str  # Temporary session ID from in-memory storage
    resume_id: Optional[str] = None


class CreateProfileRequest(BaseModel):
    """Request to create/update user profile"""
    full_name: str
    email: str
    phone: Optional[str] = None
    experience_level: Optional[str] = None


class CreateResumeRequest(BaseModel):
    """Request to create resume record"""
    file_name: str
    file_url: str
    file_size: Optional[int] = None
    parsed_data: Optional[dict] = None


# =====================================================
# USER PROFILE ENDPOINTS
# =====================================================

@router.post("/profile")
async def create_profile_endpoint(
    request: CreateProfileRequest,
    user: dict = Depends(get_current_user)
):
    """
    Create or update user profile
    Protected route - requires authentication
    """
    try:
        user_id = user["user_id"]
        
        profile = await upsert_user_profile(
            user_id=user_id,
            full_name=request.full_name,
            email=request.email,
            phone=request.phone,
            experience_level=request.experience_level
        )
        
        logger.info(f"✅ Profile created/updated for user {user_id}")
        
        return {
            "success": True,
            "profile": profile
        }
        
    except Exception as e:
        logger.error(f"Error creating profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile")
async def get_profile_endpoint(
    user: dict = Depends(get_current_user)
):
    """
    Get current user's profile
    Protected route - requires authentication
    """
    try:
        user_id = user["user_id"]
        
        profile = await get_user_profile(user_id)
        
        return {
            "success": True,
            "profile": profile
        }
        
    except Exception as e:
        logger.error(f"Error fetching profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume")
async def create_resume_endpoint(
    request: CreateResumeRequest,
    user: dict = Depends(get_current_user)
):
    """
    Create resume record from JSON data
    Protected route - requires authentication
    """
    try:
        user_id = user["user_id"]
        
        resume = await insert_resume(
            user_id=user_id,
            file_name=request.file_name,
            file_url=request.file_url,
            parsed_json=request.parsed_data,
            file_size_bytes=request.file_size
        )
        
        logger.info(f"✅ Resume record created for user {user_id}")
        
        return {
            "success": True,
            "resume_id": resume.get("id"),
            "resume": resume
        }
        
    except Exception as e:
        logger.error(f"Error creating resume record: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# RESUME ENDPOINTS
# =====================================================

@router.post("/resumes/upload")
async def upload_resume_endpoint(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """
    Upload resume and save to database
    Protected route - requires authentication
    """
    try:
        user_id = user["user_id"]
        
        # Validate file type
        if not file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Read file content
        file_content = await file.read()
        
        # Upload to Supabase Storage
        logger.info(f"📤 Uploading resume for user {user_id}: {file.filename}")
        file_url = await upload_resume_to_storage(
            user_id=user_id,
            file_content=file_content,
            file_name=file.filename
        )
        logger.info(f"✅ Resume uploaded to storage: {file_url}")
        
        # Parse resume (optional - don't fail if parsing fails)
        parsed_data = {}
        try:
            from ..services.resume_parser import parse_resume_with_llm
            logger.info(f"🔍 Parsing resume with LLM...")
            parsed_data = parse_resume_with_llm(file_content)
            logger.info(f"✅ Resume parsed successfully")
        except Exception as parse_error:
            logger.warning(f"⚠️ Could not parse resume with LLM: {parse_error} - using empty data")
            parsed_data = {
                "name": file.filename.replace(".pdf", ""),
                "skills": [],
                "experience": [],
                "education": []
            }
        
        # Insert into database
        resume_record = await insert_resume(
            user_id=user_id,
            file_name=file.filename,
            file_url=file_url,
            parsed_json=parsed_data,
            file_size_bytes=len(file_content)
        )
        
        logger.info(f"✅ Resume record created: {resume_record['id']}")
        
        return {
            "success": True,
            "resume_id": resume_record["id"],
            "file_url": file_url,
            "file_name": file.filename,
            "file_size": len(file_content),
            "parsed_data": parsed_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error uploading resume: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resumes")
async def get_resumes_endpoint(
    limit: int = 10,
    user: dict = Depends(get_current_user)
):
    """
    Get user's uploaded resumes
    Protected route - requires authentication
    """
    try:
        user_id = user["user_id"]
        
        resumes = await get_user_resumes(user_id, limit=limit)
        
        return {
            "success": True,
            "resumes": resumes,
            "total": len(resumes)
        }
        
    except Exception as e:
        logger.error(f"Error fetching resumes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/resumes/{resume_id}")
async def delete_resume_endpoint(
    resume_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Delete a resume by ID
    Protected route - requires authentication
    Only the resume owner can delete it
    """
    try:
        user_id = user["user_id"]
        
        # Verify ownership
        # Note: get_resume_by_id, _db_delete, delete_resume_from_storage are imported at top of file

        resume = await get_resume_by_id(resume_id)
        
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        if resume.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied - you can only delete your own resumes")
        
        # Delete from storage
        try:
            file_url = resume.get("file_url", "")
            if file_url:
                # Extract file path from URL
                # URL format: https://pdlzpwynoblqnhireusw.supabase.co/storage/v1/object/public/resumes/{user_id}/{timestamp}_{filename}
                # We need to extract: {user_id}/{timestamp}_{filename}
                if "/resumes/" in file_url:
                    file_path = file_url.split("/resumes/")[-1]  # Get everything after /resumes/
                    logger.info(f"🗑️ Deleting resume from storage: {file_path}")
                    deletion_result = await delete_resume_from_storage(file_path)
                    if deletion_result:
                        logger.info(f"✅ Resume file deleted from storage: {file_path}")
                    else:
                        logger.warning(f"⚠️ Could not delete from storage, but continuing with database deletion")
        except Exception as storage_error:
            logger.warning(f"⚠️ Warning during storage cleanup: {storage_error}")
            # Don't fail the request if storage deletion fails
        
        # Delete from database
        await _db_delete(
            table="resumes",
            filters={"id": resume_id}
        )
        
        logger.info(f"✅ Resume {resume_id} deleted for user {user_id}")
        
        return {
            "success": True,
            "message": "Resume deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting resume: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# SESSION ENDPOINTS
# =====================================================

@router.post("/sessions/complete")
async def complete_session_endpoint(
    request: CompleteSessionRequest,
    user: dict = Depends(get_current_user)
):
    """
    Save completed interview session to database
    
    This is called when interview completes.
    It transfers data from in-memory session to permanent database.
    """
    try:
        user_id = user["user_id"]
        
        # Get in-memory session
        from ..services.interview_session import InterviewSession
        session = InterviewSession.get_session(request.session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Verify ownership
        if session.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Prepare session data
        session_data = {
            "target_role": session.job_context.get("target_role"),
            "experience_level": session.job_context.get("experience_level"),
            "interview_type": session.job_context.get("interview_type"),
            "mode": "conversational",  # or "standard"
            "total_questions": len(session.questions),
            "answered_questions": len([r for r in session.responses if not r.get("skipped")]),
            "skipped_questions": len([r for r in session.responses if r.get("skipped")]),
            "duration_seconds": int((session.end_time - session.start_time).total_seconds()) if session.end_time else None,
            "topics_covered": list(set([q.get("category") for q in session.questions if q.get("category")]))
        }
        
        # Calculate average score if evaluations exist
        scores = [r.get("evaluation", {}).get("score") for r in session.responses 
                  if r.get("evaluation") and r.get("evaluation", {}).get("score")]
        if scores:
            session_data["average_score"] = sum(scores) / len(scores)
            
            # Determine performance tier
            avg_score = session_data["average_score"]
            if avg_score >= 8:
                session_data["performance_tier"] = "excellent"
            elif avg_score >= 6:
                session_data["performance_tier"] = "good"
            elif avg_score >= 4:
                session_data["performance_tier"] = "average"
            else:
                session_data["performance_tier"] = "needs_improvement"
        
        # Insert session into database
        db_session = await insert_completed_session(
            user_id=user_id,
            resume_id=request.resume_id,
            session_data=session_data
        )
        
        db_session_id = db_session["id"]
        
        # Prepare answers for bulk insert
        answers = []
        for idx, response in enumerate(session.responses):
            question = session.questions[idx]
            
            answer_data = {
                "question_number": idx + 1,
                "question_text": question.get("question", ""),
                "category": question.get("category"),
                "difficulty": question.get("difficulty"),
                "answer_text": response.get("answer_text", ""),
                "is_skipped": response.get("skipped", False),
                "duration_seconds": response.get("time_taken_seconds"),
                "score": response.get("evaluation", {}).get("score") if response.get("evaluation") else None,
                "evaluation_summary": response.get("evaluation") if response.get("evaluation") else None
            }
            answers.append(answer_data)
        
        # Bulk insert answers
        await insert_answers_bulk(db_session_id, answers)
        
        # Update user statistics
        await upsert_user_statistics(user_id)
        
        # Clean up in-memory session (optional)
        # InterviewSession._sessions.pop(request.session_id, None)
        
        logger.info(f"Session {request.session_id} saved to database as {db_session_id}")
        
        return {
            "success": True,
            "db_session_id": db_session_id,
            "message": "Session saved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def get_sessions_endpoint(
    limit: int = 20,
    offset: int = 0,
    user: dict = Depends(get_current_user)
):
    """
    Get user's interview sessions
    Protected route
    """
    try:
        user_id = user["user_id"]
        
        sessions = await get_user_sessions(user_id, limit=limit, offset=offset)
        
        return {
            "success": True,
            "sessions": sessions,
            "total": len(sessions)
        }
        
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session_detail_endpoint(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Get complete session details with answers
    Protected route
    """
    try:
        user_id = user["user_id"]
        
        # Get session
        session = await get_session_by_id(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Verify ownership
        if session["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get answers
        answers = await get_session_answers(session_id)
        
        return {
            "success": True,
            "session": session,
            "answers": answers
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching session detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# STATISTICS ENDPOINTS
# =====================================================

@router.get("/statistics")
async def get_statistics_endpoint(
    user: dict = Depends(get_current_user)
):
    """
    Get user's interview statistics
    Protected route
    """
    try:
        user_id = user["user_id"]
        
        stats = await get_user_statistics(user_id)
        
        if not stats:
            # No stats yet, return empty
            return {
                "success": True,
                "statistics": {
                    "total_interviews": 0,
                    "total_questions_answered": 0,
                    "average_overall_score": None
                }
            }
        
        return {
            "success": True,
            "statistics": stats
        }
        
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# DASHBOARD ENDPOINTS
# =====================================================

@router.get("/dashboard")
async def get_dashboard_endpoint(
    user: dict = Depends(get_current_user)
):
    """
    Get complete dashboard data (stats + recent sessions)
    Protected route
    """
    try:
        user_id = user["user_id"]
        
        # Get statistics
        stats = await get_user_statistics(user_id)
        
        # Get recent sessions
        recent_sessions = await get_user_sessions(user_id, limit=5)
        
        # Get resumes
        resumes = await get_user_resumes(user_id, limit=5)
        
        return {
            "success": True,
            "statistics": stats or {},
            "recent_sessions": recent_sessions,
            "resumes": resumes
        }
        
    except Exception as e:
        logger.error(f"Error fetching dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# EXAMPLE: Integration with existing main.py
# =====================================================

"""
To integrate with your existing main.py:

1. Add to imports:
   from src.routes.database_routes import router as db_router

2. Include router:
   app.include_router(db_router)

3. Update .env file:
   SUPABASE_URL=your_supabase_url
   SUPABASE_SERVICE_KEY=your_service_role_key
   SUPABASE_JWT_SECRET=your_jwt_secret

4. Install dependencies:
   pip install supabase python-jose[cryptography]

5. When interview completes, call:
   POST /api/db/sessions/complete
   with Authorization: Bearer <user_token>
"""
