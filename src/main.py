from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any
import os
import uvicorn
from dotenv import load_dotenv
from services.resume_parser import parse_resume_with_llm, validate_parsed_resume
from services.question_generator import generate_interview_questions
import logging

# Load environment variables
load_dotenv()

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

@app.get("/")
async def root():
    return {"message": "Intervu AI Backend API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "intervu-ai-backend"}

# Pydantic models
class QuestionGenerationRequest(BaseModel):
    resume_data: Dict[str, Any]
    num_questions: int = 10

@app.post("/api/resume/parse")
async def parse_resume_endpoint(
    file: UploadFile = File(...)
):
    """
    Parse resume from uploaded PDF file.
    
    Args:
        file: PDF file uploaded by user
        
    Returns:
        JSON response with parsed resume data
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400, 
                detail="Only PDF files are supported"
            )
        
        if file.size > 10 * 1024 * 1024:  # 10MB limit
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
        
        logger.info("Resume parsed successfully")
        return JSONResponse(
            content={
                "success": True,
                "data": validated_data,
                "filename": file.filename
            }
        )
        
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
    Generate interview questions based on parsed resume data.
    
    Args:
        request: QuestionGenerationRequest with resume_data and num_questions
        
    Returns:
        JSON response with generated questions
    """
    try:
        resume_data = request.resume_data
        num_questions = request.num_questions
        
        if not resume_data:
            raise HTTPException(
                status_code=400,
                detail="Resume data is required"
            )
        
        logger.info(f"Generating {num_questions} interview questions")
        questions = generate_interview_questions(resume_data, num_questions)
        
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
                "total": len(questions)
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