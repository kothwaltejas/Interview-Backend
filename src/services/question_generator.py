import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def generate_interview_questions(
    resume_data: Dict[str, Any], 
    job_context: Dict[str, Any] = None,
    num_questions: int = 10
) -> List[Dict[str, Any]]:
    """
    Generate interview questions based on parsed resume data and job context.
    
    Args:
        resume_data: Parsed resume data
        job_context: Optional job context with target_role, experience_level, interview_type
        num_questions: Number of questions to generate
        
    Returns:
        List of question dictionaries with question text and metadata
    """
    from .llm_groq_config import chat_completion
    
    try:
        # Extract key information
        name = resume_data.get('name', 'candidate')
        skills = resume_data.get('skills', [])
        experience = resume_data.get('experience', [])
        projects = resume_data.get('projects', [])
        education = resume_data.get('education', [])
        
        # Extract job context (with defaults for backward compatibility)
        target_role = "Software Developer"
        experience_level = "1-3 years"
        interview_type = "Technical"
        
        if job_context:
            target_role = job_context.get('target_role', target_role)
            experience_level = job_context.get('experience_level', experience_level)
            interview_type = job_context.get('interview_type', interview_type)
        
        # Build context for LLM
        resume_summary = f"""
Candidate Name: {name}

Skills: {', '.join(skills[:15]) if skills else 'Not specified'}

Work Experience: {len(experience)} positions
{chr(10).join([f"- {exp.get('title', 'N/A')} at {exp.get('company', 'N/A')}" for exp in experience[:3]])}

Projects: {len(projects)} projects
{chr(10).join([f"- {proj.get('title', 'N/A')} ({', '.join(proj.get('tech', [])[:3])})" for proj in projects[:3]])}

Education:
{chr(10).join([f"- {edu.get('degree', 'N/A')} from {edu.get('institution', 'N/A')}" for edu in education[:2]])}
"""

        # Adjust difficulty based on experience level
        difficulty_map = {
            "Fresher": "easy to medium",
            "1-3 years": "medium",
            "3-5 years": "medium to hard",
            "5+ years": "hard"
        }
        target_difficulty = difficulty_map.get(experience_level, "medium")

        prompt = f"""You are an expert technical interviewer conducting a {interview_type} interview for a {target_role} position.

Candidate Profile:
{resume_summary}

Interview Context:
- Target Role: {target_role}
- Experience Level: {experience_level}
- Interview Type: {interview_type}
- Target Difficulty: {target_difficulty}

CRITICAL INSTRUCTIONS - Generate EXACTLY {num_questions} questions following this structure:

Question Structure (MUST FOLLOW):
- Question 1: Introduction question - "Hi {name}, please introduce yourself and tell us about your background."
- Questions 2-3: Deep dive into their TOP 2 projects (ask about technical decisions, challenges, architecture, scalability)
- Questions 4-6: Role-specific technical questions based on {target_role} and their skills
- Questions 7-8: Scenario-based / problem-solving questions relevant to {target_role}
- Question 9: Behavioral question about teamwork, leadership, or challenges
- Question 10: Closing question about their learning, goals, or passion for the role

QUALITY RULES:
1. Make questions CONVERSATIONAL and natural - like a real interviewer would ask
2. Avoid generic textbook questions - be SPECIFIC to their resume
3. Questions should be progressively challenging
4. If interview_type is "HR", focus more on behavioral/soft skills
5. If "Technical", focus more on technical depth
6. If "Mixed", balance both

Return ONLY a JSON array with NO markdown, NO explanations:
[
  {{
    "id": 1,
    "question": "Hi {name}, please introduce yourself and tell us about your background.",
    "category": "introduction",
    "difficulty": "easy",
    "focus_area": "background",
    "expected_duration_seconds": 90
  }},
  {{
    "id": 2,
    "question": "specific project question for their first major project",
    "category": "project",
    "difficulty": "medium",
    "focus_area": "project name",
    "expected_duration_seconds": 180
  }}
]

Generate {num_questions} questions NOW as valid JSON:"""

        response = chat_completion(prompt, max_tokens=2048)
        
        if not response:
            logger.error("No response from LLM for question generation")
            return generate_fallback_questions(name, skills, projects)
        
        # Clean and parse JSON
        cleaned = response.strip()
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]
        if cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        # Find JSON array
        start = cleaned.find('[')
        end = cleaned.rfind(']')
        if start != -1 and end != -1:
            cleaned = cleaned[start:end+1]
        
        questions = json.loads(cleaned)
        
        # Validate structure
        if not isinstance(questions, list):
            raise ValueError("Response is not a list")
        
        # Ensure first question is introduction
        if len(questions) > 0:
            questions[0] = {
                "id": 1,
                "question": f"Hi {name}, please introduce yourself and tell us about your background.",
                "category": "introduction",
                "difficulty": "easy",
                "focus_area": "background",
                "expected_duration_seconds": 90
            }
        
        logger.info(f"Generated {len(questions)} interview questions for {target_role} ({experience_level})")
        return questions
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in question generation: {e}")
        return generate_fallback_questions(name, skills, projects, job_context)
    except Exception as e:
        logger.error(f"Error generating questions: {e}")
        return generate_fallback_questions(name, skills, projects, job_context)


def generate_fallback_questions(
    name: str, 
    skills: List[str], 
    projects: List[Dict],
    job_context: Dict[str, Any] = None
) -> List[Dict[str, Any]]:
    """Generate fallback questions if LLM fails."""
    
    target_role = "Software Developer"
    if job_context:
        target_role = job_context.get('target_role', target_role)
    
    questions = [
        {
            "id": 1,
            "question": f"Hi {name}, please introduce yourself and tell us about your background.",
            "category": "introduction",
            "difficulty": "easy",
            "focus_area": "background",
            "expected_duration_seconds": 90
        }
    ]
    
    # Add project questions
    if projects and len(projects) > 0:
        project = projects[0]
        questions.append({
            "id": 2,
            "question": f"Can you walk me through your {project.get('title', 'project')}? What was your role and what technologies did you use?",
            "category": "project",
            "difficulty": "medium",
            "focus_area": project.get('title', 'project'),
            "expected_duration_seconds": 180
        })
        
        if len(projects) > 1:
            project2 = projects[1]
            questions.append({
                "id": 3,
                "question": f"What challenges did you face while working on {project2.get('title', 'your project')} and how did you overcome them?",
                "category": "project",
                "difficulty": "medium",
                "focus_area": project2.get('title', 'project'),
                "expected_duration_seconds": 180
            })
    
    # Add technical questions based on skills
    if skills:
        for i, skill in enumerate(skills[:5], start=len(questions) + 1):
            questions.append({
                "id": i,
                "question": f"Can you explain your experience with {skill}? How have you used it in your projects?",
                "category": "technical",
                "difficulty": "medium",
                "focus_area": skill,
                "expected_duration_seconds": 150
            })
    
    # Add behavioral question
    questions.append({
        "id": len(questions) + 1,
        "question": "Tell me about a time when you had to work under pressure or face a tight deadline. How did you handle it?",
        "category": "behavioral",
        "difficulty": "medium",
        "focus_area": "soft skills",
        "expected_duration_seconds": 120
    })
    
    return questions[:10]
