from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
import os
import uvicorn
from dotenv import load_dotenv
from pathlib import Path

# IMPORTANT: Load .env FIRST before any other imports that need environment variables
# Find .env file (could be in current dir or parent dir)
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env from: {env_path}")
else:
    load_dotenv()  # Try default location
    print(f"⚠️ .env not found at {env_path}, using default")

# Now import services and database modules (after .env is loaded)
from services.resume_parser import parse_resume_with_llm, validate_parsed_resume
from services.question_generator import generate_interview_questions
from services.interview_session import InterviewSession
from services.answer_evaluator import evaluate_answer, batch_evaluate_session
from services.conversational_interviewer import generate_interviewer_response, generate_opening_question
import logging

# Database and Auth imports
try:
    from routes.database_routes import router as db_router
    from auth.supabase_auth import get_optional_user, get_current_user
    from database.supabase_client import (
        insert_resume, 
        upload_resume_to_storage,
        insert_completed_session,
        insert_answers_bulk,
        upsert_user_statistics,
        upsert_user_profile
    )
    SUPABASE_ENABLED = True
    print("✅ Supabase integration enabled")
except ImportError as e:
    SUPABASE_ENABLED = False
    print(f"⚠️ Supabase not configured: {e}")
except Exception as e:
    SUPABASE_ENABLED = False
    print(f"❌ Supabase error: {e}")

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Intervu AI Backend",
    description="AI-powered interview preparation backend services",
    version="1.0.0"
)

# Configure CORS
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request, call_next):
    logger.info(f"🌐 {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"📤 Response: {response.status_code}")
    return response

# Include database routes if Supabase is enabled
if SUPABASE_ENABLED:
    app.include_router(db_router)
    logger.info("✅ Database routes registered at /api/db/*")

@app.get("/")
async def root():
    return {
        "message": "Intervu AI Backend API", 
        "status": "running",
        "database": "connected" if SUPABASE_ENABLED else "disabled"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "intervu-ai-backend"}

# Pydantic models
class QuestionGenerationRequest(BaseModel):
    resume_data: Dict[str, Any]
    job_context: Optional[Dict[str, Any]] = None
    num_questions: int = 10

class SessionCreateRequest(BaseModel):
    user_id: str
    resume_data: Dict[str, Any]
    job_context: Dict[str, Any]
    num_questions: int = 10
    resume_id: Optional[str] = None  # Database ID of uploaded resume

class AnswerSubmitRequest(BaseModel):
    session_id: str
    answer_text: str
    time_taken_seconds: Optional[int] = None

class SkipQuestionRequest(BaseModel):
    session_id: str

class EvaluateAnswerRequest(BaseModel):
    question: str
    answer: str
    job_context: Dict[str, Any]
    question_metadata: Optional[Dict[str, Any]] = None

class ConversationalAnswerRequest(BaseModel):
    session_id: str
    answer_text: str
    time_taken_seconds: Optional[int] = None

# Safe dependency wrapper for optional user authentication
async def get_user_if_authenticated(request: Request) -> Optional[dict]:
    """Get user if authenticated, returns None otherwise"""
    if not SUPABASE_ENABLED:
        return None
    try:
        return await get_optional_user(request)
    except Exception as e:
        logger.warning(f"Auth check failed: {e}")
        return None

@app.post("/api/resume/parse")
async def parse_resume_endpoint(
    request: Request,
    file: UploadFile = File(...)
):
    """
    Parse resume from uploaded PDF file.
    Optionally saves to database if user is authenticated.
    
    Args:
        file: PDF file uploaded by user
        
    Returns:
        JSON response with parsed resume data
    """
    try:
        # Get authenticated user (if any)
        user = await get_user_if_authenticated(request)
        
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400, 
                detail="Only PDF files are supported"
            )
        
        if file.size and file.size > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(
                status_code=400, 
                detail="File size must be less than 10MB"
            )
        
        # Read file content
        file_content = await file.read()
        
        if not file_content:
            raise HTTPException(
                status_code=400, 
                detail="Empty file uploaded"
            )
        
        # Parse resume using AI service
        logger.info(f"Parsing resume: {file.filename}")
        parsed_data = parse_resume_with_llm(file_content)
        
        # Validate and clean the parsed data
        validated_data = validate_parsed_resume(parsed_data)
        
        if "error" in validated_data:
            logger.error(f"Resume parsing failed: {validated_data['error']}")
            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "error": validated_data["error"],
                    "details": validated_data.get("raw_response", "")
                }
            )
        
        response_data = {
            "success": True,
            "data": validated_data,
            "filename": file.filename
        }
        
        # Log authentication status
        logger.info(f"📋 Resume parse request - SUPABASE_ENABLED: {SUPABASE_ENABLED}, User authenticated: {user is not None}")
        
        # Save to database if user is authenticated and Supabase is enabled
        if SUPABASE_ENABLED and user:
            try:
                user_id = user["user_id"]
                logger.info(f"💾 Starting database save for user: {user_id}")
                
                # Upload to Supabase Storage
                logger.info(f"📤 Uploading to Supabase Storage...")
                file_url = await upload_resume_to_storage(
                    user_id=user_id,
                    file_content=file_content,
                    file_name=file.filename
                )
                logger.info(f"✅ File uploaded to: {file_url}")
                
                # Save to database
                logger.info(f"💾 Inserting resume record to database...")
                resume_record = await insert_resume(
                    user_id=user_id,
                    file_name=file.filename,
                    file_url=file_url,
                    parsed_json=validated_data,
                    file_size_bytes=len(file_content)
                )
                logger.info(f"✅ Resume record created with ID: {resume_record['id']}")
                
                # Create/update user profile
                logger.info(f"👤 Creating/updating user profile...")
                await upsert_user_profile(
                    user_id=user_id,
                    full_name=validated_data.get('name'),
                    email=user.get('email')
                )
                logger.info(f"✅ User profile updated")
                
                response_data["resume_id"] = resume_record["id"]
                response_data["saved_to_database"] = True
                logger.info(f"🎉 Resume saved to database successfully for user {user_id}")
                
            except Exception as db_error:
                logger.error(f"❌ Failed to save resume to database: {db_error}", exc_info=True)
                response_data["saved_to_database"] = False
                response_data["db_error"] = str(db_error)
        else:
            if not SUPABASE_ENABLED:
                logger.warning(f"⚠️ SUPABASE not enabled - resume not saved to database")
            elif not user:
                logger.warning(f"⚠️ No authenticated user - resume not saved to database")
            response_data["saved_to_database"] = False
        
        logger.info("Resume parsed successfully")
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error parsing resume: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.post("/api/questions/generate")
async def generate_questions_endpoint(request: QuestionGenerationRequest):
    """
    Generate interview questions based on parsed resume data and job context.
    
    Args:
        request: QuestionGenerationRequest with resume_data, job_context, and num_questions
        
    Returns:
        JSON response with generated questions
    """
    try:
        resume_data = request.resume_data
        job_context = request.job_context
        num_questions = request.num_questions
        
        if not resume_data:
            raise HTTPException(
                status_code=400,
                detail="Resume data is required"
            )
        
        logger.info(f"Generating {num_questions} interview questions")
        questions = generate_interview_questions(resume_data, job_context, num_questions)
        
        if not questions:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate questions"
            )
        
        logger.info(f"Successfully generated {len(questions)} questions")
        return JSONResponse(
            content={
                "success": True,
                "questions": questions,
                "total": len(questions),
                "job_context": job_context
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating questions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate questions: {str(e)}"
        )

@app.post("/api/session/create")
async def create_session_endpoint(request: SessionCreateRequest):
    """
    Create a new interactive interview session.
    
    Args:
        request: SessionCreateRequest with user_id, resume_data, job_context
        
    Returns:
        Session ID and first question
    """
    try:
        # Generate questions first
        questions = generate_interview_questions(
            request.resume_data,
            request.job_context,
            request.num_questions
        )
        
        if not questions:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate questions"
            )
        
        # Create session
        session = InterviewSession.create_session(
            user_id=request.user_id,
            resume_data=request.resume_data,
            questions=questions,
            job_context=request.job_context
        )
        
        # Get first question
        first_question = session.get_current_question()
        
        logger.info(f"Session created: {session.session_id}")
        
        return JSONResponse(
            content={
                "success": True,
                "session_id": session.session_id,
                "total_questions": len(questions),
                "current_question": first_question,
                "job_context": request.job_context
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create session: {str(e)}"
        )

@app.post("/api/session/create-conversational")
async def create_conversational_session_endpoint(request: SessionCreateRequest):
    """
    Create a new conversational interview session.
    Uses natural opening question and conversational flow.
    
    Args:
        request: SessionCreateRequest with user_id, resume_data, job_context
        
    Returns:
        Session ID and opening question
    """
    try:
        # Generate all questions upfront (same as standard mode)
        questions = generate_interview_questions(
            request.resume_data,
            request.job_context,
            request.num_questions
        )
        
        if not questions:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate questions"
            )
        
        # Generate natural opening question
        opening_question = generate_opening_question(
            request.resume_data,
            request.job_context
        )
        
        # Replace first question with natural opening
        questions[0] = {
            "id": 1,
            "question": opening_question,
            "category": "introduction",
            "difficulty": "easy",
            "focus_area": "background",
            "expected_duration_seconds": 90
        }
        
        # Prepare metadata with resume_id if provided
        metadata = {}
        if request.resume_id:
            metadata["resume_id"] = request.resume_id
        
        session = InterviewSession.create_session(
            user_id=request.user_id,
            resume_data=request.resume_data,
            questions=questions,
            job_context=request.job_context,
            metadata=metadata
        )
        
        first_question = session.get_current_question()
        
        logger.info(f"Conversational session created: {session.session_id}")
        
        return JSONResponse(
            content={
                "success": True,
                "mode": "conversational",
                "session_id": session.session_id,
                "total_questions": request.num_questions,
                "opening_question": first_question,
                "job_context": request.job_context
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating conversational session: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create conversational session: {str(e)}"
        )

@app.get("/api/session/{session_id}")
async def get_session_endpoint(session_id: str):
    """Get current state of an interview session."""
    try:
        session = InterviewSession.get_session(session_id)
        
        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )
        
        current_question = session.get_current_question()
        
        return JSONResponse(
            content={
                "success": True,
                "session_id": session.session_id,
                "status": session.status.value,
                "current_question": current_question,
                "progress": {
                    "current": session.current_question_index + 1,
                    "total": len(session.questions)
                }
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving session: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve session: {str(e)}"
        )

@app.post("/api/session/answer")
async def submit_answer_endpoint(request: AnswerSubmitRequest):
    """Submit an answer for the current question."""
    try:
        session = InterviewSession.get_session(request.session_id)
        
        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )
        
        # Get current question before submitting
        current_question = session.get_current_question()
        
        if not current_question:
            raise HTTPException(
                status_code=400,
                detail="No active question to answer"
            )
        
        # Evaluate the answer
        evaluation = evaluate_answer(
            question=current_question['question'],
            candidate_answer=request.answer_text,
            job_context=session.job_context,
            question_metadata={
                'category': current_question.get('category'),
                'difficulty': current_question.get('difficulty'),
                'focus_area': current_question.get('focus_area')
            }
        )
        
        # Submit answer (this moves to next question)
        result = session.submit_answer(
            answer_text=request.answer_text,
            time_taken_seconds=request.time_taken_seconds
        )
        
        # Add evaluation to the last response
        if session.responses:
            session.responses[-1].update({
                'score': evaluation.get('score'),
                'feedback': evaluation.get('feedback'),
                'follow_up_question': evaluation.get('follow_up_question')
            })
        
        return JSONResponse(
            content={
                "success": True,
                "evaluation": evaluation,
                "result": result
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting answer: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit answer: {str(e)}"
        )

@app.post("/api/session/skip")
async def skip_question_endpoint(request: SkipQuestionRequest):
    """Skip the current question."""
    try:
        session = InterviewSession.get_session(request.session_id)
        
        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )
        
        # Set skip flag for next interviewer response
        session.skip_flag = True
        
        # Reset follow_up_count when skipping
        session.follow_up_count = 0
        
        result = session.skip_question()
        
        return JSONResponse(
            content={
                "success": True,
                "result": result
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error skipping question: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to skip question: {str(e)}"
        )

@app.get("/api/session/{session_id}/summary")
async def get_session_summary_endpoint(
    request: Request,
    session_id: str
):
    """
    Get complete summary of interview session.
    Optionally saves to database if user is authenticated.
    """
    try:
        # Get authenticated user (if any)
        user = await get_user_if_authenticated(request)
        
        session = InterviewSession.get_session(session_id)
        
        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )
        
        summary = session.get_session_summary()
        
        # Add overall evaluation
        overall_eval = batch_evaluate_session(
            session.responses,
            session.job_context
        )
        
        summary['overall_evaluation'] = overall_eval
        
        response_data = {
            "success": True,
            "summary": summary
        }
        
        # Log authentication status
        logger.info(f"📊 Session summary request - SUPABASE_ENABLED: {SUPABASE_ENABLED}, User authenticated: {user is not None}")
        
        # Save to database if user is authenticated and Supabase is enabled
        if SUPABASE_ENABLED and user:
            try:
                user_id = user["user_id"]
                logger.info(f"💾 Starting session save for user: {user_id}")
                
                # DEBUG: Log session job_context
                logger.info(f"🔍 DEBUG: session.job_context = {session.job_context}")
                
                # Calculate answered and skipped questions
                answered_count = len([r for r in session.responses if r.get("answer_text") and not r.get("skipped")])
                skipped_count = len([r for r in session.responses if r.get("skipped")])
                
                # DEBUG: Log responses for answer inspection
                logger.info(f"🔍 DEBUG: session.responses count = {len(session.responses)}")
                for idx, resp in enumerate(session.responses):
                    logger.info(f"🔍 DEBUG: Response {idx+1}: answer_text={repr(resp.get('answer_text', 'MISSING'))[:50]}, skipped={resp.get('skipped')}")
                
                # Prepare session data with correct field names
                session_data = {
                    "target_role": session.job_context.get("target_role", "Unknown"),
                    "experience_level": session.job_context.get("experience_level", "Unknown"),
                    "interview_type": session.job_context.get("interview_type", "technical"),
                    "mode": "conversational",
                    "total_questions": len(session.questions),
                    "answered_questions": answered_count,
                    "skipped_questions": skipped_count,
                    "duration_seconds": summary.get("duration_seconds", 0),
                    "average_score": overall_eval.get("overall_score"),
                    "performance_tier": overall_eval.get("performance_tier"),
                    "overall_feedback": overall_eval.get("summary", ""),
                    "topics_covered": list(set([q.get("category", "General") for q in session.questions if q.get("category")]))
                }
                
                # DEBUG: Log session_data being sent to database
                logger.info(f"🔍 DEBUG: session_data = {session_data}")
                
                # Find resume_id if available (from session metadata)
                resume_id = session.metadata.get("resume_id") if hasattr(session, 'metadata') else None
                logger.info(f"📎 Resume ID from session: {resume_id}")
                
                # Insert completed session
                logger.info(f"💾 Inserting session to database...")
                db_session = await insert_completed_session(
                    user_id=user_id,
                    resume_id=resume_id,
                    session_data=session_data
                )
                
                db_session_id = db_session["id"]
                logger.info(f"✅ Session saved with ID: {db_session_id}")
                
                # Prepare answers for bulk insert with correct field names
                answers = []
                for idx, response in enumerate(session.responses):
                    question = session.questions[idx] if idx < len(session.questions) else {}
                    answers.append({
                        "question_number": idx + 1,
                        "question_text": question.get("question", ""),
                        "category": question.get("category", "General"),
                        "difficulty": question.get("difficulty", "medium"),
                        "answer_text": response.get("answer_text", ""),
                        "is_skipped": response.get("skipped", False),
                        "duration_seconds": response.get("time_taken_seconds"),
                        "score": response.get("evaluation", {}).get("score") if response.get("evaluation") else None,
                        "evaluation_summary": response.get("evaluation", {}).get("summary") if response.get("evaluation") else None
                    })
                
                # Insert answers
                if answers:
                    logger.info(f"💾 Inserting {len(answers)} answers...")
                    await insert_answers_bulk(db_session_id, answers)
                    logger.info(f"✅ Answers inserted")
                
                # Update user statistics
                logger.info(f"📊 Updating user statistics...")
                await upsert_user_statistics(user_id)
                logger.info(f"✅ Statistics updated")
                
                response_data["saved_to_database"] = True
                response_data["db_session_id"] = db_session_id
                logger.info(f"🎉 Session {session_id} saved to database successfully for user {user_id}")
                
            except Exception as db_error:
                logger.error(f"❌ Failed to save session to database: {db_error}", exc_info=True)
                response_data["saved_to_database"] = False
                response_data["db_error"] = str(db_error)
        else:
            if not SUPABASE_ENABLED:
                logger.warning(f"⚠️ SUPABASE not enabled - session not saved to database")
            elif not user:
                logger.warning(f"⚠️ No authenticated user - session not saved to database")
            response_data["saved_to_database"] = False
        
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session summary: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get session summary: {str(e)}"
        )

@app.post("/api/session/conversational-answer")
async def conversational_answer_endpoint(request: ConversationalAnswerRequest):
    """
    Submit an answer and get a natural, conversational interviewer response.
    No scores or evaluations - just like a real interview.
    """
    try:
        session = InterviewSession.get_session(request.session_id)
        
        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )
        
        current_question_data = session.get_current_question()
        
        if not current_question_data:
            raise HTTPException(
                status_code=400,
                detail="No active question to answer"
            )
        
        # Get conversational response from interviewer
        logger.info(f"Generating conversational response for session {request.session_id}")
        
        # Get current topic from question metadata
        current_topic = current_question_data.get('category', 'technical')
        
        # Determine if topic changed
        topic_changed = (session.previous_topic and 
                        session.previous_topic != current_topic)
        
        # Reset follow_up_count if topic changed
        if topic_changed:
            session.follow_up_count = 0
            session.previous_topic = current_topic
            if current_topic not in session.topics_used:
                session.topics_used.append(current_topic)
        
        # Generate interviewer response with state
        interviewer_response = generate_interviewer_response(
            current_question=current_question_data.get('question', ''),
            candidate_answer=request.answer_text,
            resume_context=session.resume_data,
            job_context=session.job_context,
            follow_up_count=session.follow_up_count,
            skip_flag=session.skip_flag,
            previous_topic=session.previous_topic,
            topics_used=session.topics_used
        )
        
        # Reset skip flag after processing
        session.skip_flag = False
        
        # Update conversation history
        session.conversation_history.append({
            'role': 'candidate',
            'message': request.answer_text
        })
        session.conversation_history.append({
            'role': 'interviewer',
            'message': interviewer_response
        })
        
        # Record the answer (without evaluation for now)
        result = session.submit_answer(
            answer_text=request.answer_text,
            time_taken_seconds=request.time_taken_seconds
        )
        
        # Check if interview is complete
        next_question = session.get_current_question()
        is_complete = next_question is None
        
        response_data = {
            "success": True,
            "interviewer_response": interviewer_response,
            "is_complete": is_complete
        }
        
        if not is_complete:
            response_data["next_question"] = next_question
            response_data["progress"] = {
                "current": session.current_question_index + 1,
                "total": len(session.questions)
            }
        
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in conversational answer: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process answer: {str(e)}"
        )

@app.post("/api/evaluate/answer")
async def evaluate_answer_endpoint(request: EvaluateAnswerRequest):
    """Evaluate a single answer (standalone endpoint)."""
    try:
        evaluation = evaluate_answer(
            question=request.question,
            candidate_answer=request.answer,
            job_context=request.job_context,
            question_metadata=request.question_metadata
        )
        
        return JSONResponse(
            content={
                "success": True,
                "evaluation": evaluation
            }
        )
        
    except Exception as e:
        logger.error(f"Error evaluating answer: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to evaluate answer: {str(e)}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating questions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate questions: {str(e)}"
        )


# =====================================================
# SPEECH-TO-TEXT ENDPOINT (Voice Interview Interface)
# =====================================================
# This is an INTERFACE LAYER only - does NOT modify interview logic
# The STT service is modular and can be swapped with any provider

# Lazy import to avoid breaking existing functionality if STT not installed
STT_AVAILABLE = False
try:
    from services.speech_to_text import transcribe_audio, is_stt_available
    STT_AVAILABLE = is_stt_available()
    if STT_AVAILABLE:
        logger.info("✅ Speech-to-Text service available")
    else:
        logger.warning("⚠️ Speech-to-Text dependencies not installed")
except ImportError as e:
    logger.warning(f"⚠️ Speech-to-Text service not available: {e}")


@app.get("/api/audio/stt/status")
async def stt_status_endpoint():
    """
    Check if STT service is available.
    Frontend uses this to decide whether to show voice mode option.
    """
    return JSONResponse(content={
        "available": STT_AVAILABLE,
        "message": "STT service is ready" if STT_AVAILABLE else "STT requires faster-whisper installation"
    })


@app.post("/api/audio/stt")
async def speech_to_text_endpoint(
    audio: UploadFile = File(...),
    language: str = "en"
):
    """
    Convert speech audio to text using local Whisper model.
    
    This endpoint is designed to be:
    - MODULAR: Can be swapped with any STT provider
    - SIMPLE: Just audio in, text out
    - DECOUPLED: Does NOT touch interview/session logic
    
    The frontend sends audio, gets text, then uses existing
    text-based endpoints for interview logic.
    
    Args:
        audio: Audio file (webm, wav, mp3 supported)
        language: Language code (default: en)
    
    Returns:
        JSON with transcript and confidence score
    
    Flow:
        Frontend MediaRecorder -> This endpoint -> Clean text
        Clean text -> Existing /api/session/conversational-answer
    """
    if not STT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Speech-to-Text service not available. Install faster-whisper: pip install faster-whisper"
        )
    
    try:
        # Read audio file
        audio_bytes = await audio.read()
        
        if not audio_bytes:
            raise HTTPException(
                status_code=400,
                detail="Empty audio file received"
            )
        
        # Determine audio format from filename
        filename = audio.filename or "audio.webm"
        audio_format = filename.split(".")[-1].lower()
        
        # Supported formats
        supported_formats = ["webm", "wav", "mp3", "m4a", "ogg", "flac"]
        if audio_format not in supported_formats:
            audio_format = "webm"  # Default assumption for browser MediaRecorder
        
        logger.info(f"🎤 Received audio: {len(audio_bytes)} bytes, format: {audio_format}")
        
        # Transcribe using Whisper
        transcript, confidence = transcribe_audio(
            audio_bytes=audio_bytes,
            audio_format=audio_format,
            language=language
        )
        
        # Return clean response
        return JSONResponse(content={
            "success": True,
            "transcript": transcript,
            "confidence": round(confidence, 2),
            "language": language,
            "audio_size_bytes": len(audio_bytes)
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ STT failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Speech-to-Text processing failed: {str(e)}"
        )


if __name__ == "__main__":
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 8000))
    
    logger.info(f"Starting Intervu AI Backend on {host}:{port}")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level=os.getenv('LOG_LEVEL', 'info').lower()
    )