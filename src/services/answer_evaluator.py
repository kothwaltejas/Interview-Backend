import json
import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def evaluate_answer(
    question: str,
    candidate_answer: str,
    job_context: Dict[str, Any],
    question_metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Evaluate candidate's answer using LLM.
    
    Args:
        question: The interview question asked
        candidate_answer: Candidate's response
        job_context: Job context with target_role, experience_level, interview_type
        question_metadata: Additional metadata (category, difficulty, focus_area)
        
    Returns:
        Dictionary with feedback, score, and optional follow-up question
    """
    from .llm_groq_config import chat_completion
    
    # Handle empty or skipped answers
    if not candidate_answer or len(candidate_answer.strip()) < 10:
        return {
            "feedback": "No substantial answer provided. Consider elaborating on your response.",
            "score": 1,
            "follow_up_question": None
        }
    
    try:
        target_role = job_context.get('target_role', 'the position')
        experience_level = job_context.get('experience_level', 'your level')
        interview_type = job_context.get('interview_type', 'Technical')
        
        category = "general"
        if question_metadata:
            category = question_metadata.get('category', 'general')
        
        # Build evaluation prompt
        prompt = f"""You are an expert technical interviewer evaluating a candidate for a {target_role} position ({experience_level} experience).

Interview Type: {interview_type}
Question Category: {category}

Question Asked:
"{question}"

Candidate's Answer:
"{candidate_answer}"

Evaluate this answer based on:
1. Relevance to the question
2. Technical accuracy (if applicable)
3. Communication clarity
4. Depth of knowledge
5. Whether answer matches experience level expectations

Provide:
- Short, constructive feedback (2-3 sentences max)
- Score from 1-10
- Follow-up question ONLY if answer is weak/incomplete (optional)

Return ONLY valid JSON with NO markdown:
{{
  "feedback": "constructive feedback here",
  "score": 7,
  "follow_up_question": "optional follow-up if needed" 
}}

Evaluate NOW:"""

        response = chat_completion(prompt, max_tokens=512)
        
        if not response:
            logger.error("No response from LLM for answer evaluation")
            return generate_fallback_evaluation(candidate_answer)
        
        # Clean and parse JSON
        cleaned = clean_json_response(response)
        evaluation = json.loads(cleaned)
        
        # Validate structure
        if not isinstance(evaluation, dict):
            raise ValueError("Response is not a dictionary")
        
        # Ensure required fields
        if 'feedback' not in evaluation:
            evaluation['feedback'] = "Answer received."
        if 'score' not in evaluation:
            evaluation['score'] = 5
        if 'follow_up_question' not in evaluation:
            evaluation['follow_up_question'] = None
        
        # Validate score range
        try:
            evaluation['score'] = max(1, min(10, int(evaluation['score'])))
        except:
            evaluation['score'] = 5
        
        logger.info(f"Answer evaluated - Score: {evaluation['score']}")
        return evaluation
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in answer evaluation: {e}")
        return generate_fallback_evaluation(candidate_answer)
    except Exception as e:
        logger.error(f"Error evaluating answer: {e}")
        return generate_fallback_evaluation(candidate_answer)


def clean_json_response(response: str) -> str:
    """Clean and extract JSON from LLM response."""
    if not response:
        return "{}"
    
    # Remove markdown code blocks
    response = re.sub(r'```json\s*', '', response, flags=re.IGNORECASE)
    response = re.sub(r'```\s*', '', response)
    
    # Remove any text before the first {
    first_brace = response.find('{')
    if first_brace != -1:
        response = response[first_brace:]
    
    # Remove any text after the last }
    last_brace = response.rfind('}')
    if last_brace != -1:
        response = response[:last_brace + 1]
    
    # Fix common JSON issues
    response = response.replace('\n', ' ')
    response = re.sub(r',\s*}', '}', response)  # Remove trailing commas
    response = re.sub(r',\s*]', ']', response)  # Remove trailing commas in arrays
    
    return response.strip() or "{}"


def generate_fallback_evaluation(answer: str) -> Dict[str, Any]:
    """Generate fallback evaluation if LLM fails."""
    
    answer_length = len(answer.strip())
    
    if answer_length < 50:
        return {
            "feedback": "Your answer is quite brief. Try to provide more details and examples.",
            "score": 4,
            "follow_up_question": "Can you elaborate more on this with specific examples?"
        }
    elif answer_length < 150:
        return {
            "feedback": "Good start! Consider adding more depth and specific examples to strengthen your answer.",
            "score": 6,
            "follow_up_question": None
        }
    else:
        return {
            "feedback": "Thank you for the detailed response. Make sure your answer directly addresses all aspects of the question.",
            "score": 7,
            "follow_up_question": None
        }


def batch_evaluate_session(responses: list, job_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate all responses in a session and provide overall assessment.
    
    Args:
        responses: List of question-answer pairs from session
        job_context: Job context information
        
    Returns:
        Overall evaluation with average score and feedback
    """
    if not responses:
        return {
            "overall_score": 0,
            "average_score": 0,
            "total_questions": 0,
            "answered": 0,
            "skipped": 0,
            "feedback": "No responses to evaluate."
        }
    
    total_score = 0
    evaluated_count = 0
    
    for response in responses:
        if not response.get('skipped', False):
            # Individual evaluation already done during session
            # This is for aggregation
            if 'score' in response:
                total_score += response['score']
                evaluated_count += 1
    
    average_score = total_score / evaluated_count if evaluated_count > 0 else 0
    
    # Performance tiers
    if average_score >= 8:
        overall_feedback = "Excellent performance! Strong technical knowledge and communication skills."
    elif average_score >= 6:
        overall_feedback = "Good performance overall. Some areas could use more depth."
    elif average_score >= 4:
        overall_feedback = "Fair performance. Consider strengthening your technical knowledge and practice articulating your thoughts."
    else:
        overall_feedback = "Needs improvement. Focus on understanding core concepts and practice interview skills."
    
    return {
        "overall_score": round(average_score, 1),
        "average_score": round(average_score, 1),
        "total_questions": len(responses),
        "answered": len([r for r in responses if not r.get('skipped', False)]),
        "skipped": len([r for r in responses if r.get('skipped', False)]),
        "feedback": overall_feedback,
        "performance_tier": "Excellent" if average_score >= 8 else "Good" if average_score >= 6 else "Fair" if average_score >= 4 else "Needs Improvement"
    }
