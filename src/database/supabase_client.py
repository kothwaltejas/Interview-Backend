"""
Supabase Database Client
Handles all database operations for Interview AI platform
Uses Supabase SDK for storage and direct HTTP for REST API
"""

import os
import logging
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load .env from correct path
env_path = Path(__file__).parent.parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

logger = logging.getLogger(__name__)

# Initialize Supabase SDK client
try:
    from supabase import create_client
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
    
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("✅ Supabase SDK client initialized for storage operations")
    else:
        supabase = None
        logger.error("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")
except Exception as e:
    logger.error(f"❌ Failed to initialize Supabase SDK: {e}")
    supabase = None


class SupabaseDB:
    """Supabase database client using direct HTTP"""
    
    _url: Optional[str] = None
    _key: Optional[str] = None
    
    @classmethod
    def _init(cls):
        """Initialize URL and key"""
        if cls._url is None:
            cls._url = os.getenv("SUPABASE_URL")
            cls._key = os.getenv("SUPABASE_SERVICE_KEY")
            
            if not cls._url or not cls._key:
                raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
            
            logger.info("Supabase HTTP client initialized")
    
    @classmethod
    def get_headers(cls) -> Dict[str, str]:
        """Get headers for Supabase API requests"""
        cls._init()
        return {
            "apikey": cls._key,
            "Authorization": f"Bearer {cls._key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    @classmethod
    def get_rest_url(cls) -> str:
        """Get REST API URL"""
        cls._init()
        return f"{cls._url}/rest/v1"
    
    @classmethod
    def get_storage_url(cls) -> str:
        """Get Storage API URL"""
        cls._init()
        return f"{cls._url}/storage/v1"


# =====================================================
# HTTP HELPERS
# =====================================================

async def _db_insert(table: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a record into a table"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SupabaseDB.get_rest_url()}/{table}",
            headers=SupabaseDB.get_headers(),
            json=data
        )
        response.raise_for_status()
        result = response.json()
        return result[0] if result else {}


async def _db_select(
    table: str,
    filters: Dict[str, Any] = None,
    columns: str = "*",
    order_by: str = None,
    desc: bool = True,
    limit: int = None,
    offset: int = None,
    single: bool = False
) -> Any:
    """Select records from a table"""
    url = f"{SupabaseDB.get_rest_url()}/{table}?select={columns}"
    
    if filters:
        for key, value in filters.items():
            url += f"&{key}=eq.{value}"
    
    if order_by:
        direction = "desc" if desc else "asc"
        url += f"&order={order_by}.{direction}"
    
    if limit:
        url += f"&limit={limit}"
    
    if offset:
        url += f"&offset={offset}"
    
    headers = SupabaseDB.get_headers()
    if single:
        headers["Accept"] = "application/vnd.pgrst.object+json"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 406:  # No rows found for single
            return None
        response.raise_for_status()
        return response.json()


async def _db_upsert(table: str, data: Dict[str, Any], conflict_column: str = "id") -> Dict[str, Any]:
    """Upsert (insert or update) a record"""
    headers = SupabaseDB.get_headers()
    # Use resolution=merge-duplicates for upsert behavior
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    
    async with httpx.AsyncClient() as client:
        # Add on_conflict parameter to URL for proper upsert
        url = f"{SupabaseDB.get_rest_url()}/{table}?on_conflict={conflict_column}"
        response = await client.post(
            url,
            headers=headers,
            json=data
        )
        response.raise_for_status()
        result = response.json()
        return result[0] if result else {}


async def _db_delete(table: str, filters: Dict[str, Any]) -> bool:
    """Delete records from a table with filters"""
    headers = SupabaseDB.get_headers()
    
    async with httpx.AsyncClient() as client:
        url = f"{SupabaseDB.get_rest_url()}/{table}"
        
        # Build filter query
        filter_parts = []
        for key, value in filters.items():
            filter_parts.append(f"{key}=eq.{value}")
        
        if filter_parts:
            url += "?" + "&".join(filter_parts)
        
        response = await client.delete(url, headers=headers)
        response.raise_for_status()
        return True


def _extract_resume_storage_path(file_url: str) -> Optional[str]:
    if not file_url or "/resumes/" not in file_url:
        return None

    file_path = file_url.split("/resumes/", 1)[1]
    return file_path.split("?", 1)[0]


async def _refresh_resume_file_url(file_url: str) -> str:
    file_path = _extract_resume_storage_path(file_url)
    if not file_path or not supabase:
        return file_url

    try:
        signed_url_response = supabase.storage.from_("resumes").create_signed_url(
            file_path,
            expires_in=2592000
        )
        signed_url = signed_url_response.get("signedURL") if isinstance(signed_url_response, dict) else signed_url_response
        return signed_url or file_url
    except Exception as e:
        logger.warning(f"⚠️ Could not refresh signed URL for {file_path}: {e}")
        return file_url


# =====================================================
# RESUME OPERATIONS
# =====================================================

async def insert_resume(
    user_id: str,
    file_name: str,
    file_url: str,
    parsed_json: Dict[str, Any],
    file_size_bytes: int = None
) -> Dict[str, Any]:
    """
    Insert a new resume record
    """
    try:
        # Extract summary data
        skills = parsed_json.get('skills', []) if parsed_json else []
        experience = parsed_json.get('experience', []) if parsed_json else []
        
        # Calculate years of experience
        experience_years = len(experience) if experience else 0
        
        name = parsed_json.get('name', 'Unknown') if parsed_json else 'Unknown'
        resume_summary = f"{name} - {len(skills)} skills, {experience_years} years experience"
        
        data = {
            "user_id": user_id,
            "file_name": file_name,
            "file_url": file_url,
            "file_size_bytes": file_size_bytes,
            "parsed_json": parsed_json or {},
            "resume_summary": resume_summary,
            "skills": skills[:20] if skills else [],
            "experience_years": experience_years
        }
        
        result = await _db_insert("resumes", data)
        logger.info(f"Resume inserted for user {user_id}")
        return result
            
    except Exception as e:
        logger.error(f"Error inserting resume: {e}")
        raise


async def get_user_resumes(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get user's resumes"""
    try:
        result = await _db_select(
            table="resumes",
            filters={"user_id": user_id},
            order_by="created_at",
            desc=True,
            limit=limit
        )
        resumes = result if result else []
        refreshed_resumes = []
        for resume in resumes:
            refreshed_resume = dict(resume)
            refreshed_resume["file_url"] = await _refresh_resume_file_url(resume.get("file_url", ""))
            refreshed_resumes.append(refreshed_resume)
        return refreshed_resumes
        
    except Exception as e:
        logger.error(f"Error fetching resumes: {e}")
        raise


async def get_resume_by_id(resume_id: str) -> Optional[Dict[str, Any]]:
    """Get specific resume by ID"""
    try:
        resume = await _db_select(
            table="resumes",
            filters={"id": resume_id},
            single=True
        )
        if resume:
            resume = dict(resume)
            resume["file_url"] = await _refresh_resume_file_url(resume.get("file_url", ""))
        return resume
    except Exception as e:
        logger.error(f"Error fetching resume: {e}")
        return None


# =====================================================
# INTERVIEW SESSION OPERATIONS
# =====================================================

async def insert_completed_session(
    user_id: str,
    resume_id: Optional[str],
    session_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Insert a completed interview session"""
    try:
        data = {
            "user_id": user_id,
            "resume_id": resume_id,
            "target_role": session_data.get("target_role"),
            "experience_level": session_data.get("experience_level"),
            "interview_type": session_data.get("interview_type"),
            "mode": session_data.get("mode"),
            "total_questions": session_data.get("total_questions"),
            "answered_questions": session_data.get("answered_questions"),
            "skipped_questions": session_data.get("skipped_questions"),
            "duration_seconds": session_data.get("duration_seconds"),
            "average_score": session_data.get("average_score"),
            "performance_tier": session_data.get("performance_tier"),
            "overall_feedback": session_data.get("overall_feedback"),
            "topics_covered": session_data.get("topics_covered", [])
        }
        
        result = await _db_insert("interview_sessions", data)
        logger.info(f"Session inserted for user {user_id}")
        return result
            
    except Exception as e:
        logger.error(f"Error inserting session: {e}")
        raise


async def get_user_sessions(
    user_id: str,
    limit: int = 20,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Get user's interview sessions"""
    try:
        result = await _db_select(
            table="interview_sessions",
            filters={"user_id": user_id},
            order_by="completed_at",
            desc=True,
            limit=limit,
            offset=offset
        )
        return result if result else []
        
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        raise


async def get_session_by_id(session_id: str) -> Optional[Dict[str, Any]]:
    """Get specific session by ID"""
    try:
        return await _db_select(
            table="interview_sessions",
            filters={"id": session_id},
            single=True
        )
    except Exception as e:
        logger.error(f"Error fetching session: {e}")
        return None


# =====================================================
# INTERVIEW ANSWERS OPERATIONS
# =====================================================

async def insert_answers_bulk(
    session_id: str,
    answers: List[Dict[str, Any]]
) -> bool:
    """Bulk insert interview answers"""
    try:
        answer_records = []
        for answer in answers:
            record = {
                "session_id": session_id,
                "question_number": answer.get("question_number"),
                "question_text": answer.get("question_text"),
                "category": answer.get("category"),
                "difficulty": answer.get("difficulty"),
                "answer_text": answer.get("answer_text", ""),
                "is_skipped": answer.get("is_skipped", False),
                "word_count": len(answer.get("answer_text", "").split()) if answer.get("answer_text") else 0,
                "duration_seconds": answer.get("duration_seconds"),
                "score": answer.get("score"),
                "evaluation_summary": answer.get("evaluation_summary")
            }
            answer_records.append(record)
        
        # Bulk insert using REST API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SupabaseDB.get_rest_url()}/interview_answers",
                headers=SupabaseDB.get_headers(),
                json=answer_records
            )
            response.raise_for_status()
        
        logger.info(f"Inserted {len(answer_records)} answers for session {session_id}")
        return True
            
    except Exception as e:
        logger.error(f"Error inserting answers: {e}")
        raise


async def insert_answer_evaluation(
    session_id: str,
    user_id: str,
    question_index: int,
    question_text: str,
    answer_text: str,
    evaluation: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Persist a per-answer evaluation result to the answer_evaluations table.

    Extracts scalar fields (score, llm_score, rule_score, llm_used, etc.) from
    the evaluation dict and stores the full dict as evaluation_metadata (JSONB).

    Args:
        session_id:      In-memory session ID (TEXT, not a FK constraint)
        user_id:         UUID of the authenticated user
        question_index:  0-based index of the question within the session
        question_text:   The interview question that was asked
        answer_text:     The candidate's verbatim answer
        evaluation:      Full dict returned by EnhancedEvaluationService

    Returns:
        The inserted row dict, or {} on failure (caller must handle silently)
    """
    import json as _json

    metadata = evaluation.get("metadata", {})

    composite = evaluation.get("composite", {})

    data = {
        "session_id": session_id,
        "user_id": user_id,
        "question_index": question_index,
        "question_text": question_text,
        "answer_text": answer_text,
        "score": float(evaluation.get("average_score", 0)),
        "llm_score": float(evaluation.get("average_score", 0)) if not metadata.get("fallback") else None,
        "rule_score": None,
        "llm_used": not bool(metadata.get("fallback")) and not evaluation.get("llm_used") is False,
        "dataset_match_type": (
            "strong" if metadata.get("strong_match")
            else "weak" if metadata.get("dataset_match")
            else "none"
        ),
        "difficulty": evaluation.get("difficulty"),
        "evaluation_metadata": evaluation.get("evaluation_metadata", evaluation),
        "voice_score": composite.get("sector_scores", {}).get("voice", {}).get("score"),
        "camera_score": composite.get("sector_scores", {}).get("camera", {}).get("score"),
        "composite_score": composite.get("composite_score"),
        "voice_metrics": composite.get("sector_scores", {}).get("voice", {}).get("metrics"),
        "camera_metrics": composite.get("sector_scores", {}).get("camera", {}).get("metrics"),
    }

    result = await _db_insert("answer_evaluations", data)
    logger.info(
        f"📝 Evaluation persisted — session={session_id} "
        f"q_idx={question_index} score={data['score']}"
    )
    return result


async def get_session_answers(session_id: str) -> List[Dict[str, Any]]:
    """Get all answers for a session"""
    try:
        result = await _db_select(
            table="interview_answers",
            filters={"session_id": session_id},
            order_by="question_number",
            desc=False
        )
        return result if result else []
        
    except Exception as e:
        logger.error(f"Error fetching answers: {e}")
        raise


# =====================================================
# USER STATISTICS OPERATIONS
# =====================================================

async def upsert_user_statistics(user_id: str) -> bool:
    """Calculate and update user statistics"""
    try:
        sessions = await get_user_sessions(user_id, limit=1000)
        
        if not sessions:
            return True
        
        total_interviews = len(sessions)
        total_questions_answered = sum(s.get("answered_questions", 0) for s in sessions)
        
        scores = [s.get("average_score") for s in sessions if s.get("average_score")]
        average_overall_score = sum(scores) / len(scores) if scores else None
        
        roles = [s.get("target_role") for s in sessions if s.get("target_role")]
        most_common_role = max(set(roles), key=roles.count) if roles else None
        
        total_time_spent_seconds = sum(s.get("duration_seconds", 0) or 0 for s in sessions)
        last_interview_at = sessions[0].get("completed_at") if sessions else None
        
        stats_data = {
            "user_id": user_id,
            "total_interviews": total_interviews,
            "total_questions_answered": total_questions_answered,
            "average_overall_score": average_overall_score,
            "most_common_role": most_common_role,
            "total_time_spent_seconds": total_time_spent_seconds,
            "last_interview_at": last_interview_at
        }
        
        await _db_upsert("interview_statistics", stats_data, "user_id")
        logger.info(f"Statistics updated for user {user_id}")
        return True
            
    except Exception as e:
        logger.error(f"Error updating statistics: {e}")
        return False


async def get_user_statistics(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user statistics"""
    try:
        return await _db_select(
            table="interview_statistics",
            filters={"user_id": user_id},
            single=True
        )
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        return None


# =====================================================
# USER PROFILE OPERATIONS
# =====================================================

async def upsert_user_profile(
    user_id: str,
    full_name: str = None,
    email: str = None,
    phone: str = None,
    experience_level: str = None,
    avatar_url: str = None
) -> Dict[str, Any]:
    """Insert or update user profile"""
    try:
        data = {"id": user_id}
        if full_name:
            data["full_name"] = full_name
        if email:
            data["email"] = email
        if phone:
            data["phone"] = phone
        if experience_level:
            data["experience_level"] = experience_level
        if avatar_url:
            data["avatar_url"] = avatar_url
        
        result = await _db_upsert("user_profiles", data, "id")
        logger.info(f"Profile upserted for user {user_id}")
        return result
            
    except Exception as e:
        logger.error(f"Error upserting profile: {e}")
        raise


async def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user profile"""
    try:
        return await _db_select(
            table="user_profiles",
            filters={"id": user_id},
            single=True
        )
    except Exception as e:
        logger.error(f"Error fetching profile: {e}")
        return None


# =====================================================
# STORAGE OPERATIONS (Supabase Storage via SDK)
# =====================================================

async def upload_resume_to_storage(
    user_id: str,
    file_content: bytes,
    file_name: str
) -> str:
    """Upload resume PDF to Supabase Storage using SIGNED URLs (secure)"""
    try:
        if not supabase:
            raise Exception("Supabase client not initialized - check SUPABASE_URL and SUPABASE_SERVICE_KEY")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = f"{user_id}/{timestamp}_{file_name}"
        
        logger.info(f"📤 Uploading resume to bucket 'resumes': {file_path}")
        
        # Use Supabase SDK to upload file
        response = supabase.storage.from_("resumes").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": "application/pdf"}
        )
        
        # Generate signed URL (valid for 30 days)
        # Signed URLs don't require bucket to be public and prevent 404 Bucket not found errors
        try:
            signed_url_response = supabase.storage.from_("resumes").create_signed_url(
                file_path,
                expires_in=2592000  # 30 days in seconds
            )
            signed_url = signed_url_response.get("signedURL") or signed_url_response
            logger.info(f"✅ Resume uploaded successfully: {file_path}")
            logger.info(f"📎 Signed URL (30 days): {signed_url}")
            return signed_url
        except Exception as url_error:
            logger.warning(f"⚠️ Could not generate signed URL: {url_error}")
            # Fallback to public URL if signed URL generation fails
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/resumes/{file_path}"
            logger.info(f"📎 Using public URL: {public_url}")
            return public_url
            
    except Exception as e:
        logger.error(f"❌ Error uploading resume: {e}")
        raise


async def delete_resume_from_storage(file_path: str) -> bool:
    """Delete resume from storage using SDK"""
    try:
        if not supabase:
            raise Exception("Supabase client not initialized")
        
        # Extract just the path part if full URL is passed
        if "/storage/" in file_path:
            file_path = file_path.split("/resumes/", 1)[1] if "/resumes/" in file_path else file_path
        
        logger.info(f"🗑️ Deleting resume from storage: {file_path}")
        
        # Use Supabase SDK to delete file
        response = supabase.storage.from_("resumes").remove([file_path])
        
        logger.info(f"✅ Resume deleted successfully: {file_path}")
        return True
            
    except Exception as e:
        logger.error(f"❌ Error deleting resume: {e}")
        return False
