"""
Conversational Interviewer Service
Provides natural, professional interviewer responses during interactive sessions.
Enhanced with human-like behavior rules and structured topic management.
"""

import logging
from typing import Dict, Optional, List
from .llm_groq_config import chat_completion

logger = logging.getLogger(__name__)


def generate_interviewer_response(
    current_question: str,
    candidate_answer: str,
    resume_context: Dict = None,
    job_context: Dict = None,
    follow_up_count: int = 0,
    skip_flag: bool = False,
    previous_topic: str = None,
    topics_used: List[str] = None
) -> Optional[str]:
    """
    Generate a natural interviewer response that acknowledges the answer.
    Implements human-like behavior rules for topic rotation and follow-ups.
    
    Args:
        current_question: The question that was just answered
        candidate_answer: The candidate's response
        resume_context: Optional resume data for context
        job_context: Optional job context (role, level, type)
        follow_up_count: Number of consecutive follow-ups on same topic
        skip_flag: Whether the previous question was skipped
        previous_topic: The topic of the previous question
        topics_used: List of topics already covered
        
    Returns:
        Interviewer's natural acknowledgment
    """
    
    # Initialize topics_used if None
    if topics_used is None:
        topics_used = []
    
    # Build context for more relevant responses
    context_info = ""
    if job_context:
        target_role = job_context.get('target_role', 'Software Developer')
        experience_level = job_context.get('experience_level', '1-3 years')
        context_info = f"\nTarget Role: {target_role}\nExperience Level: {experience_level}"
    
    # --- BEHAVIOR RULES ENGINE ---
    
    behavioral_instruction = ""
    
    # Rule 1: Handle skip flag
    if skip_flag:
        behavioral_instruction = """
IMPORTANT: The candidate skipped the previous question.
- Be supportive and understanding.
- Say something like "No worries, we can come back to that later."
- Do NOT repeat the same question.
- Smoothly transition to a new topic.
"""
    
    # Rule 2: Handle excessive follow-ups
    elif follow_up_count >= 2:
        behavioral_instruction = """
IMPORTANT: You've asked 2 follow-ups already on this topic.
- Stop digging deeper.
- Acknowledge briefly and naturally.
- Use a smooth transition like "Alright, let's shift gears a bit..."
- Move to a different topic.
"""
    
    # Rule 3: Weak answer handling
    elif len(candidate_answer.split()) < 15:
        behavioral_instruction = """
The answer seems brief.
- Do NOT say "wrong" or "too short".
- Give gentle encouragement.
- Acknowledge what they said positively.
"""
    
    # --- MASTER SYSTEM PROMPT ---
    
    system_prompt = f"""You are a highly experienced human interviewer conducting a real job interview.

Your goal is to simulate a REAL interview — natural, thoughtful, and human.

IMPORTANT RULES:
- Speak naturally, not robotic.
- NO scoring, NO evaluation language.
- NO bullet points.
- 1-2 sentences maximum (2-3 lines).
- React to candidate's answer genuinely.
- Acknowledge VERY briefly before the next question is asked.
- Avoid repeating same transition phrases.
- Maintain professional but warm tone.
- Sound like an actual person, not an AI.
- Keep it SHORT and crisp.

{behavioral_instruction}

TOPIC ROTATION:
- Avoid dwelling too long on one topic.
- Balance between: projects, technical skills, problem-solving, behavioral, role-specific.

Never mention internal logic like follow_up_count, topics, or skip_flag.
Just be natural and human."""

    user_prompt = f"""Current Question:
{current_question}

Candidate Answer:
{candidate_answer}
{context_info}

Your job:
Acknowledge their answer naturally like a real human interviewer would.

Guidelines:
- Be VERY brief (1-2 sentences, maximum 2-3 lines)
- Sound natural and conversational
- NO questions (the next question comes separately)
- NO scores or evaluations
- Show genuine interest but keep it short
- Professional but friendly tone
- Get to the point quickly

Return ONLY the brief acknowledgment as plain text."""

    try:
        response = chat_completion(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=60,  # Very short responses (2-3 lines)
            temperature=0.5   # More natural variation
        )
        
        if not response:
            logger.error("No response from LLM for interviewer response")
            return generate_fallback_response(candidate_answer, skip_flag)
        
        return response.strip()
        
    except Exception as e:
        logger.error(f"Error generating interviewer response: {e}")
        return generate_fallback_response(candidate_answer, skip_flag)


def generate_fallback_response(answer: str, skip_flag: bool = False) -> str:
    """
    Generate a simple fallback response if LLM fails.
    Provides natural acknowledgments without questions.
    
    Args:
        answer: The candidate's answer
        skip_flag: Whether question was skipped
        
    Returns:
        Natural fallback acknowledgment
    """
    
    # Handle skip case
    if skip_flag:
        return "No worries, we can revisit that later."
    
    answer_length = len(answer.split())
    
    # Brief answer fallback
    if answer_length < 15:
        return "I see. Thanks for that."
    
    # Natural acknowledgments (no questions) - very short
    fallback_responses = [
        "Thanks for sharing.",
        "I see. Good context.",
        "Got it. Interesting.",
        "Understood.",
        "That makes sense.",
        "Okay, thanks.",
        "Interesting.",
        "Alright, clear."
    ]
    
    # Rotate through fallbacks based on answer hash
    index = hash(answer) % len(fallback_responses)
    return fallback_responses[index]


def generate_opening_question(
    resume_data: Dict,
    job_context: Dict = None
) -> str:
    """
    Generate a natural, personalized opening question for the interview.
    Greets candidate by name and asks them to introduce themselves.
    
    Args:
        resume_data: Parsed resume information
        job_context: Optional job context (role, level, type)
        
    Returns:
        Natural opening greeting and question
    """
    
    # Extract candidate name
    username = resume_data.get('name', 'there')
    if not username or username == 'Not found':
        username = 'there'
    
    # Extract job context
    target_role = 'Software Developer'
    experience_level = '1-3 years'
    
    if job_context:
        target_role = job_context.get('target_role', 'Software Developer')
        experience_level = job_context.get('experience_level', '1-3 years')
    
    # --- ENHANCED SYSTEM PROMPT FOR OPENING ---
    
    system_prompt = f"""You are a professional, friendly human interviewer conducting a real job interview.

Candidate Name: {username}
Target Role: {target_role}
Experience Level: {experience_level}

Start the interview naturally.

Your first message must:
- Greet the candidate by name
- Welcome them warmly
- Ask them to briefly introduce themselves
- Ask them to highlight key projects they have worked on

Tone:
- Friendly but professional
- Natural spoken English
- 2–4 sentences max
- Not robotic
- Sound like a real person starting an interview"""

    user_prompt = f"""Generate the opening question for the interview.

Candidate: {username}
Role: {target_role}
Level: {experience_level}

Create a natural greeting that:
1. Greets them by name
2. Welcomes them
3. Asks for a brief self-introduction
4. Asks them to mention key projects

Keep it conversational and human. 2-4 sentences."""

    try:
        response = chat_completion(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=150,
            temperature=0.6  # Slight variation for naturalness
        )
        
        if response:
            return response.strip()
        
        # Fallback to template
        logger.warning("LLM failed for opening question, using template")
        return generate_opening_fallback(username, target_role)
        
    except Exception as e:
        logger.error(f"Error generating opening question: {e}")
        return generate_opening_fallback(username, target_role)


def generate_opening_fallback(username: str, target_role: str) -> str:
    """
    Fallback opening question if LLM fails.
    
    Args:
        username: Candidate's name
        target_role: Target role they're applying for
        
    Returns:
        Natural opening question
    """
    if username and username != 'there':
        return f"Hi {username}, thanks for joining me today! I'd love to hear a bit about yourself and your background. Could you walk me through your experience and tell me about some key projects you've worked on?"
    else:
        return f"Hi there, thanks for joining me today! I'd love to hear a bit about yourself and your background. Could you walk me through your experience and tell me about some key projects you've worked on?"


def generate_closing_response(session_summary: Dict) -> str:
    """
    Generate a natural closing statement for the interview.
    
    Args:
        session_summary: Summary of the interview session
        
    Returns:
        Natural closing statement
    """
    responses = [
        "Thank you for your time today. We've covered a lot of ground, and I appreciate your detailed answers. We'll be in touch soon regarding next steps.",
        "That wraps up our interview. I appreciate you sharing your experiences with me. The team will review everything and get back to you shortly.",
        "Great, we're all set. Thanks for walking me through your background and projects. We'll follow up with you about next steps in the coming days."
    ]
    
    import random
    return random.choice(responses)
