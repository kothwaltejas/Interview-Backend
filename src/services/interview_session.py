import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class InterviewSession:
    """Manages an interactive interview session."""
    
    # In-memory storage (will be replaced with database)
    _sessions: Dict[str, Dict[str, Any]] = {}
    
    def __init__(
        self,
        user_id: str,
        resume_data: Dict[str, Any],
        questions: List[Dict[str, Any]],
        job_context: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.session_id = str(uuid.uuid4())
        self.user_id = user_id
        self.resume_data = resume_data
        self.questions = questions
        self.job_context = job_context
        self.status = SessionStatus.IN_PROGRESS
        self.current_question_index = 0
        self.responses: List[Dict[str, Any]] = []
        self.start_time = datetime.utcnow()
        self.end_time = None
        self.metadata = metadata or {}  # Store additional data like resume_id
        
        # Conversational interview state management
        self.follow_up_count = 0
        self.skip_flag = False
        self.previous_topic = None
        self.topics_used: List[str] = []
        self.conversation_history: List[Dict[str, str]] = []
        
        # Store session in memory
        InterviewSession._sessions[self.session_id] = self
        logger.info(f"Created interview session {self.session_id} for user {user_id}")
    
    @classmethod
    def get_session(cls, session_id: str) -> Optional['InterviewSession']:
        """Retrieve an existing session."""
        return cls._sessions.get(session_id)
    
    @classmethod
    def create_session(
        cls,
        user_id: str,
        resume_data: Dict[str, Any],
        questions: List[Dict[str, Any]],
        job_context: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> 'InterviewSession':
        """Create a new interview session."""
        return cls(user_id, resume_data, questions, job_context, metadata)
    
    def get_current_question(self) -> Optional[Dict[str, Any]]:
        """Get the current question to be answered."""
        if self.status != SessionStatus.IN_PROGRESS:
            return None
        
        if self.current_question_index >= len(self.questions):
            self.complete_session()
            return None
        
        question = self.questions[self.current_question_index].copy()
        question['question_number'] = self.current_question_index + 1
        question['total_questions'] = len(self.questions)
        question['session_id'] = self.session_id
        
        return question
    
    def submit_answer(self, answer_text: str, time_taken_seconds: Optional[int] = None) -> Dict[str, Any]:
        """Submit an answer for the current question."""
        if self.status != SessionStatus.IN_PROGRESS:
            raise ValueError("Session is not in progress")
        
        if self.current_question_index >= len(self.questions):
            raise ValueError("No more questions available")
        
        current_question = self.questions[self.current_question_index]
        
        response = {
            "question_id": current_question.get('id', self.current_question_index + 1),
            "question_text": current_question.get('question', ''),
            "answer_text": answer_text,
            "skipped": False,
            "time_taken_seconds": time_taken_seconds,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.responses.append(response)
        self.current_question_index += 1
        
        logger.info(f"Answer submitted for session {self.session_id}, question {current_question.get('id', self.current_question_index)}")
        
        # Check if interview is complete
        if self.current_question_index >= len(self.questions):
            self.complete_session()
            return {
                "status": "completed",
                "message": "Interview completed successfully!",
                "total_questions": len(self.questions),
                "answered": len([r for r in self.responses if not r['skipped']]),
                "skipped": len([r for r in self.responses if r['skipped']])
            }
        
        return {
            "status": "success",
            "message": "Answer recorded",
            "next_question": self.get_current_question()
        }
    
    def skip_question(self) -> Dict[str, Any]:
        """Skip the current question."""
        if self.status != SessionStatus.IN_PROGRESS:
            raise ValueError("Session is not in progress")
        
        if self.current_question_index >= len(self.questions):
            raise ValueError("No more questions available")
        
        current_question = self.questions[self.current_question_index]
        
        response = {
            "question_id": current_question.get('id', self.current_question_index + 1),
            "question_text": current_question.get('question', ''),
            "answer_text": "",
            "skipped": True,
            "time_taken_seconds": 0,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.responses.append(response)
        self.current_question_index += 1
        
        logger.info(f"Question skipped for session {self.session_id}, question {current_question.get('id', self.current_question_index)}")
        
        # Check if interview is complete
        if self.current_question_index >= len(self.questions):
            self.complete_session()
            return {
                "status": "completed",
                "message": "Interview completed!",
                "total_questions": len(self.questions),
                "answered": len([r for r in self.responses if not r['skipped']]),
                "skipped": len([r for r in self.responses if r['skipped']])
            }
        
        return {
            "status": "skipped",
            "message": "Question skipped",
            "next_question": self.get_current_question()
        }
    
    def complete_session(self):
        """Mark the session as completed."""
        self.status = SessionStatus.COMPLETED
        self.end_time = datetime.utcnow()
        logger.info(f"Session {self.session_id} completed")
    
    def abandon_session(self):
        """Mark the session as abandoned."""
        self.status = SessionStatus.ABANDONED
        self.end_time = datetime.utcnow()
        logger.info(f"Session {self.session_id} abandoned")
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the session."""
        duration_seconds = 0
        if self.end_time and self.start_time:
            duration_seconds = int((self.end_time - self.start_time).total_seconds())
        
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "status": self.status.value,
            "job_context": self.job_context,
            "total_questions": len(self.questions),
            "questions_answered": self.current_question_index,
            "answered_count": len([r for r in self.responses if not r['skipped']]),
            "skipped_count": len([r for r in self.responses if r['skipped']]),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": duration_seconds,
            "responses": self.responses
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return self.get_session_summary()
