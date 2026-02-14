"""
Supabase Database Client
Handles all database operations for Interview AI platform
Uses direct HTTP requests to avoid SDK dependency issues
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
    headers["Prefer"] = f"resolution=merge-duplicates,return=representation"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SupabaseDB.get_rest_url()}/{table}",
            headers=headers,
            json=data
        )
        response.raise_for_status()
        result = response.json()
        return result[0] if result else {}


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
        return result if result else []
        
    except Exception as e:
        logger.error(f"Error fetching resumes: {e}")
        raise


async def get_resume_by_id(resume_id: str) -> Optional[Dict[str, Any]]:
    """Get specific resume by ID"""
    try:
        return await _db_select(
            table="resumes",
            filters={"id": resume_id},
            single=True
        )
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
        
        # DEBUG: Log the data being inserted
        logger.info(f"🔍 DEBUG: Session insert data - target_role='{data['target_role']}', experience_level='{data['experience_level']}'")
        
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
            # DEBUG: Log each answer record
            logger.info(f"🔍 DEBUG: Answer record {record['question_number']}: answer_text='{record['answer_text'][:50] if record['answer_text'] else 'EMPTY'}...', is_skipped={record['is_skipped']}")
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
# STORAGE OPERATIONS (Supabase Storage via HTTP)
# =====================================================

async def upload_resume_to_storage(
    user_id: str,
    file_content: bytes,
    file_name: str
) -> str:
    """Upload resume PDF to Supabase Storage using direct HTTP"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = f"{user_id}/{timestamp}_{file_name}"
        
        storage_url = f"{SupabaseDB.get_storage_url()}/object/resumes/{file_path}"
        
        headers = {
            "apikey": SupabaseDB._key,
            "Authorization": f"Bearer {SupabaseDB._key}",
            "Content-Type": "application/pdf"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                storage_url,
                headers=headers,
                content=file_content
            )
            response.raise_for_status()
        
        # Return public URL
        public_url = f"{SupabaseDB._url}/storage/v1/object/public/resumes/{file_path}"
        logger.info(f"Resume uploaded: {file_path}")
        return public_url
            
    except Exception as e:
        logger.error(f"Error uploading resume: {e}")
        raise


async def delete_resume_from_storage(file_path: str) -> bool:
    """Delete resume from storage"""
    try:
        storage_url = f"{SupabaseDB.get_storage_url()}/object/resumes/{file_path}"
        
        headers = {
            "apikey": SupabaseDB._key,
            "Authorization": f"Bearer {SupabaseDB._key}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.delete(storage_url, headers=headers)
            response.raise_for_status()
        
        logger.info(f"Resume deleted: {file_path}")
        return True
            
    except Exception as e:
        logger.error(f"Error deleting resume: {e}")
        return False
