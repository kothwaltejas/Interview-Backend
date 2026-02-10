import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def generate_interview_questions(resume_data: Dict[str, Any], num_questions: int = 10) -> List[Dict[str, Any]]:
    """
    Generate interview questions based on parsed resume data.
    
    Args:
        resume_data: Parsed resume data
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

        prompt = f"""You are an expert technical interviewer. Based on the candidate's resume, generate {num_questions} interview questions.

Resume Summary:
{resume_summary}

IMPORTANT RULES:
1. Question 1 MUST be: "Hi {name}, please introduce yourself and tell us about your background."
2. Questions 2-3 MUST focus on their projects (ask about technical decisions, challenges, implementation details)
3. Questions 4-{num_questions} should be technical questions focused on their skills, experience, and resume content
4. Questions should be progressively challenging
5. Questions should be specific to technologies and experiences mentioned in their resume
6. Avoid generic questions - make them personalized to this candidate

Return ONLY a JSON array in this exact format:
[
  {{
    "id": 1,
    "question": "Hi {name}, please introduce yourself and tell us about your background.",
    "category": "introduction",
    "difficulty": "easy",
    "focus_area": "background"
  }},
  {{
    "id": 2,
    "question": "specific project question here",
    "category": "project",
    "difficulty": "medium",
    "focus_area": "project name or technology"
  }}
]

Generate {num_questions} questions now:"""

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
                "focus_area": "background"
            }
        
        logger.info(f"Generated {len(questions)} interview questions")
        return questions
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in question generation: {e}")
        return generate_fallback_questions(name, skills, projects)
    except Exception as e:
        logger.error(f"Error generating questions: {e}")
        return generate_fallback_questions(name, skills, projects)


def generate_fallback_questions(name: str, skills: List[str], projects: List[Dict]) -> List[Dict[str, Any]]:
    """Generate fallback questions if LLM fails."""
    questions = [
        {
            "id": 1,
            "question": f"Hi {name}, please introduce yourself and tell us about your background.",
            "category": "introduction",
            "difficulty": "easy",
            "focus_area": "background"
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
            "focus_area": project.get('title', 'project')
        })
        
        if len(projects) > 1:
            project2 = projects[1]
            questions.append({
                "id": 3,
                "question": f"What challenges did you face while working on {project2.get('title', 'your project')} and how did you overcome them?",
                "category": "project",
                "difficulty": "medium",
                "focus_area": project2.get('title', 'project')
            })
    
    # Add technical questions based on skills
    if skills:
        for i, skill in enumerate(skills[:5], start=len(questions) + 1):
            questions.append({
                "id": i,
                "question": f"Can you explain your experience with {skill}? How have you used it in your projects?",
                "category": "technical",
                "difficulty": "medium",
                "focus_area": skill
            })
    
    return questions[:10]
