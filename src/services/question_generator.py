"""
Question Generator - Structured Interview Question Generation

This module generates interview questions using GROQ LLM with a strict structure:
- Question 1: Introduction (fixed format)
- Questions 2-5/6: Resume-based technical with follow-ups
- Questions 6-9: Role-specific technical
- Questions 9-12: Behavioral questions

Output is clean JSON array for voice pipeline integration.
"""

import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def generate_interview_questions(
    resume_data: Dict[str, Any], 
    job_context: Dict[str, Any] = None,
    num_questions: int = 12
) -> List[Dict[str, Any]]:
    """
    Generate structured interview questions based on parsed resume data and job context.
    
    Args:
        resume_data: Parsed resume data with name, skills, experience, projects, education
        job_context: Job context with target_role, experience_level, interview_type
        num_questions: Number of questions to generate (default: 12)
        
    Returns:
        List of question dictionaries with question text and metadata
    """
    from .llm_groq_config import chat_completion
    
    try:
        # ═══════════════════════════════════════════════════════════════
        # EXTRACT RESUME DATA
        # ═══════════════════════════════════════════════════════════════
        name = resume_data.get('name', 'Candidate')
        if not name or name == 'Not found':
            name = 'Candidate'
        
        skills = resume_data.get('skills', [])
        experience = resume_data.get('experience', [])
        projects = resume_data.get('projects', [])
        education = resume_data.get('education', [])
        
        # ═══════════════════════════════════════════════════════════════
        # EXTRACT JOB CONTEXT (with defensive defaults)
        # ═══════════════════════════════════════════════════════════════
        target_role = "Software Developer"
        experience_level = "1-3 years"
        interview_type = "Technical"
        
        if job_context:
            target_role = job_context.get('target_role') or job_context.get('role') or target_role
            experience_level = job_context.get('experience_level') or experience_level
            interview_type = job_context.get('interview_type') or interview_type
        
        logger.info(f"📋 Generating questions for: {name}")
        logger.info(f"   Role: {target_role}, Level: {experience_level}, Type: {interview_type}")
        
        # ═══════════════════════════════════════════════════════════════
        # BUILD RESUME SUMMARY FOR LLM
        # ═══════════════════════════════════════════════════════════════
        skills_text = ', '.join(skills[:15]) if skills else 'Not specified'
        
        # Format experience entries
        exp_entries = []
        for exp in experience[:3]:
            title = exp.get('title', 'N/A')
            company = exp.get('company', 'N/A')
            duration = exp.get('duration', '')
            responsibilities = exp.get('responsibilities', [])
            resp_text = '; '.join(responsibilities[:2]) if responsibilities else ''
            exp_entries.append(f"- {title} at {company} ({duration}): {resp_text}")
        experience_text = '\n'.join(exp_entries) if exp_entries else 'No experience listed'
        
        # Format project entries
        proj_entries = []
        for proj in projects[:4]:
            title = proj.get('title', 'N/A')
            description = proj.get('description', '')[:100]
            tech = ', '.join(proj.get('tech', [])[:5])
            proj_entries.append(f"- {title} ({tech}): {description}")
        projects_text = '\n'.join(proj_entries) if proj_entries else 'No projects listed'
        
        # Format education
        edu_entries = []
        for edu in education[:2]:
            degree = edu.get('degree', 'N/A')
            institution = edu.get('institution', 'N/A')
            edu_entries.append(f"- {degree} from {institution}")
        education_text = '\n'.join(edu_entries) if edu_entries else 'Not specified'
        
        resume_summary = f"""
CANDIDATE PROFILE:
==================
Name: {name}

SKILLS:
{skills_text}

WORK EXPERIENCE ({len(experience)} positions):
{experience_text}

PROJECTS ({len(projects)} projects):
{projects_text}

EDUCATION:
{education_text}
"""

        # ═══════════════════════════════════════════════════════════════
        # DETERMINE DIFFICULTY BASED ON EXPERIENCE
        # ═══════════════════════════════════════════════════════════════
        difficulty_config = {
            "Fresher": {"base": "easy", "tech": "easy-medium", "behavioral": "easy"},
            "1-3 years": {"base": "medium", "tech": "medium", "behavioral": "medium"},
            "3-5 years": {"base": "medium", "tech": "medium-hard", "behavioral": "medium"},
            "5+ years": {"base": "medium", "tech": "hard", "behavioral": "medium-hard"}
        }
        difficulty = difficulty_config.get(experience_level, difficulty_config["1-3 years"])

        # ═══════════════════════════════════════════════════════════════
        # BUILD THE STRUCTURED LLM PROMPT
        # ═══════════════════════════════════════════════════════════════
        prompt = f"""You are an expert technical interviewer conducting a {interview_type} interview for a {target_role} position.

{resume_summary}

INTERVIEW CONTEXT:
==================
Target Role: {target_role}
Experience Level: {experience_level}
Interview Type: {interview_type}
Total Questions Required: {num_questions}

════════════════════════════════════════════════════════════════════════════════
STRICT QUESTION STRUCTURE - FOLLOW EXACTLY
════════════════════════════════════════════════════════════════════════════════

Generate {num_questions} questions following this EXACT structure:

╔══════════════════════════════════════════════════════════════════════════════╗
║ SECTION 1: INTRODUCTION (Question 1)                                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ - Warm, welcoming introduction                                              ║
║ - Ask candidate to introduce themselves                                     ║
║ - Ask about their background and journey                                    ║
║ - Category: "introduction"                                                  ║
║ - Difficulty: "{difficulty['base']}"                                        ║
║ - DO NOT use exact template - be natural but include same content          ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║ SECTION 2: RESUME-BASED TECHNICAL (Questions 2-5)                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Q2: Ask about their MOST impressive project from resume                     ║
║     - Mention project by NAME from their resume                             ║
║     - Ask about architecture, tech stack, their role                        ║
║     - Category: "resume_based"                                              ║
║     - Difficulty: "{difficulty['base']}"                                    ║
║                                                                              ║
║ Q3: FOLLOW-UP on Q2                                                         ║
║     - Dig deeper into challenges faced                                      ║
║     - Ask about specific implementation decisions                           ║
║     - Category: "follow_up"                                                 ║
║     - Difficulty: "{difficulty['tech']}"                                    ║
║     - Mark: "follow_up": true                                               ║
║                                                                              ║
║ Q4: Ask about ANOTHER project or specific SKILL from resume                 ║
║     - Reference actual skills/technologies from their CV                    ║
║     - Category: "resume_based"                                              ║
║     - Difficulty: "{difficulty['tech']}"                                    ║
║                                                                              ║
║ Q5: FOLLOW-UP probing question                                              ║
║     - Could be about scalability, optimization, testing                     ║
║     - Category: "follow_up"                                                 ║
║     - Difficulty: "{difficulty['tech']}"                                    ║
║     - Mark: "follow_up": true                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║ SECTION 3: ROLE-SPECIFIC TECHNICAL (Questions 6-9)                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Q6: Core technical concept for {target_role}                                ║
║     - NOT limited to their resume                                           ║
║     - Test fundamental domain knowledge                                     ║
║     - Category: "role_based"                                                ║
║     - Difficulty: "{difficulty['tech']}"                                    ║
║                                                                              ║
║ Q7: System design / Architecture question                                   ║
║     - Real-world scenario relevant to {target_role}                         ║
║     - Category: "role_based"                                                ║
║     - Difficulty: "{difficulty['tech']}"                                    ║
║                                                                              ║
║ Q8: Problem-solving / Debugging scenario                                    ║
║     - "How would you approach..." type question                             ║
║     - Category: "role_based"                                                ║
║     - Difficulty: "{difficulty['tech']}"                                    ║
║                                                                              ║
║ Q9: Advanced technical / Best practices                                     ║
║     - Security, performance, code quality                                   ║
║     - Category: "role_based"                                                ║
║     - Difficulty: "hard"                                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║ SECTION 4: BEHAVIORAL (Questions 10-12)                                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Q10: Teamwork / Collaboration                                               ║
║      - "Tell me about a time when..." format                                ║
║      - Category: "behavioral"                                               ║
║      - Difficulty: "{difficulty['behavioral']}"                             ║
║                                                                              ║
║ Q11: Conflict / Pressure handling                                           ║
║      - Deadline pressure, disagreements, challenges                         ║
║      - Category: "behavioral"                                               ║
║      - Difficulty: "{difficulty['behavioral']}"                             ║
║                                                                              ║
║ Q12: Leadership / Initiative OR Closing question                            ║
║      - Taking ownership, going beyond requirements                          ║
║      - OR "Why this role? Where do you see yourself?"                       ║
║      - Category: "behavioral"                                               ║
║      - Difficulty: "{difficulty['behavioral']}"                             ║
╚══════════════════════════════════════════════════════════════════════════════╝

════════════════════════════════════════════════════════════════════════════════
OUTPUT FORMAT - STRICT JSON ARRAY
════════════════════════════════════════════════════════════════════════════════

Return ONLY a JSON array with NO markdown, NO explanation, NO extra text:

[
  {{
    "id": 1,
    "question": "Your warm introduction question here",
    "category": "introduction",
    "difficulty": "easy",
    "focus_area": "background",
    "follow_up": false,
    "expected_duration_seconds": 90
  }},
  {{
    "id": 2,
    "question": "Specific resume-based question mentioning their project",
    "category": "resume_based",
    "difficulty": "medium",
    "focus_area": "project_name_from_resume",
    "follow_up": false,
    "expected_duration_seconds": 120
  }}
]

QUALITY RULES:
1. Be CONVERSATIONAL - sound like a real human interviewer
2. Be SPECIFIC - reference actual projects/skills from their resume by name
3. NO repetition - each question must be unique
4. NO generic questions - personalize everything
5. PROGRESSIVE difficulty - questions should get slightly harder
6. Mark follow-up questions with "follow_up": true
7. For HR/Behavioral interviews: replace some technical questions with behavioral

Generate exactly {num_questions} questions as a clean JSON array:"""

        # ═══════════════════════════════════════════════════════════════
        # CALL GROQ LLM
        # ═══════════════════════════════════════════════════════════════
        response = chat_completion(
            prompt=prompt,
            max_tokens=3000,
            temperature=0.6  # Balance between creativity and consistency
        )
        
        if not response:
            logger.error("No response from LLM for question generation")
            return generate_fallback_questions(name, skills, projects, target_role, experience_level)
        
        # ═══════════════════════════════════════════════════════════════
        # PARSE AND VALIDATE JSON RESPONSE
        # ═══════════════════════════════════════════════════════════════
        questions = parse_llm_response(response)
        
        if not questions or len(questions) == 0:
            logger.warning("Failed to parse LLM response, using fallback")
            return generate_fallback_questions(name, skills, projects, target_role, experience_level)
        
        # ═══════════════════════════════════════════════════════════════
        # ENSURE FIRST QUESTION IS ALWAYS INTRODUCTION
        # ═══════════════════════════════════════════════════════════════
        questions[0] = {
            "id": 1,
            "question": f"Hi {name}! Welcome to this interview. Please introduce yourself and tell us about your background and journey into {target_role}.",
            "category": "introduction",
            "difficulty": "easy",
            "focus_area": "background",
            "follow_up": False,
            "expected_duration_seconds": 90
        }
        
        # ═══════════════════════════════════════════════════════════════
        # VALIDATE AND FIX QUESTION STRUCTURE
        # ═══════════════════════════════════════════════════════════════
        validated_questions = validate_questions(questions, num_questions)
        
        logger.info(f"✅ Generated {len(validated_questions)} questions for {target_role} ({experience_level})")
        return validated_questions
        
    except Exception as e:
        logger.error(f"Error generating questions: {e}", exc_info=True)
        return generate_fallback_questions(
            resume_data.get('name', 'Candidate'),
            resume_data.get('skills', []),
            resume_data.get('projects', []),
            job_context.get('target_role', 'Software Developer') if job_context else 'Software Developer',
            job_context.get('experience_level', '1-3 years') if job_context else '1-3 years'
        )


def parse_llm_response(response: str) -> Optional[List[Dict[str, Any]]]:
    """
    Parse LLM response to extract JSON array.
    Handles various formatting issues.
    """
    try:
        # Clean the response
        cleaned = response.strip()
        
        # Remove markdown code blocks
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]
        elif cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        # Find JSON array boundaries
        start = cleaned.find('[')
        end = cleaned.rfind(']')
        
        if start == -1 or end == -1:
            logger.error("No JSON array found in response")
            return None
        
        json_str = cleaned[start:end+1]
        
        # Parse JSON
        questions = json.loads(json_str)
        
        if not isinstance(questions, list):
            logger.error("Parsed JSON is not a list")
            return None
        
        return questions
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"Error parsing LLM response: {e}")
        return None


def validate_questions(questions: List[Dict[str, Any]], expected_count: int) -> List[Dict[str, Any]]:
    """
    Validate and fix question structure.
    Ensures all required fields are present.
    """
    validated = []
    
    for idx, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        
        # Ensure required fields with defaults
        validated_q = {
            "id": q.get("id", idx + 1),
            "question": q.get("question", ""),
            "category": q.get("category", "technical"),
            "difficulty": q.get("difficulty", "medium"),
            "focus_area": q.get("focus_area", "general"),
            "follow_up": q.get("follow_up", False),
            "expected_duration_seconds": q.get("expected_duration_seconds", 120)
        }
        
        # Skip empty questions
        if not validated_q["question"]:
            continue
        
        # Normalize category
        category = validated_q["category"].lower().replace(" ", "_")
        valid_categories = ["introduction", "resume_based", "role_based", "behavioral", "follow_up", "technical", "project"]
        if category not in valid_categories:
            category = "technical"
        validated_q["category"] = category
        
        # Normalize difficulty
        difficulty = validated_q["difficulty"].lower()
        valid_difficulties = ["easy", "medium", "hard", "easy-medium", "medium-hard"]
        if difficulty not in valid_difficulties:
            difficulty = "medium"
        validated_q["difficulty"] = difficulty
        
        validated.append(validated_q)
    
    return validated[:expected_count]


def generate_fallback_questions(
    name: str, 
    skills: List[str], 
    projects: List[Dict],
    target_role: str = "Software Developer",
    experience_level: str = "1-3 years"
) -> List[Dict[str, Any]]:
    """
    Generate comprehensive fallback questions if LLM fails.
    Follows the same structure as LLM-generated questions.
    """
    
    questions = []
    
    # ═══════════════════════════════════════════════════════════════
    # SECTION 1: INTRODUCTION
    # ═══════════════════════════════════════════════════════════════
    questions.append({
        "id": 1,
        "question": f"Hi {name}! Welcome to this interview. Please introduce yourself and tell us about your background and journey into {target_role}.",
        "category": "introduction",
        "difficulty": "easy",
        "focus_area": "background",
        "follow_up": False,
        "expected_duration_seconds": 90
    })
    
    # ═══════════════════════════════════════════════════════════════
    # SECTION 2: RESUME-BASED (Questions 2-5)
    # ═══════════════════════════════════════════════════════════════
    if projects and len(projects) > 0:
        project = projects[0]
        project_name = project.get('title', 'your main project')
        project_tech = ', '.join(project.get('tech', [])[:3]) or 'the technologies you used'
        
        questions.append({
            "id": 2,
            "question": f"I see you worked on {project_name}. Can you walk me through the architecture and your role in building it?",
            "category": "resume_based",
            "difficulty": "medium",
            "focus_area": project_name,
            "follow_up": False,
            "expected_duration_seconds": 150
        })
        
        questions.append({
            "id": 3,
            "question": f"What were the biggest challenges you faced while building {project_name} and how did you overcome them?",
            "category": "follow_up",
            "difficulty": "medium",
            "focus_area": project_name,
            "follow_up": True,
            "expected_duration_seconds": 120
        })
    else:
        questions.append({
            "id": 2,
            "question": "Can you tell me about the most significant project you've worked on? What was your role and what technologies did you use?",
            "category": "resume_based",
            "difficulty": "medium",
            "focus_area": "projects",
            "follow_up": False,
            "expected_duration_seconds": 150
        })
        
        questions.append({
            "id": 3,
            "question": "What challenges did you face in that project and how did you solve them?",
            "category": "follow_up",
            "difficulty": "medium",
            "focus_area": "challenges",
            "follow_up": True,
            "expected_duration_seconds": 120
        })
    
    # Add skill-based questions
    if skills and len(skills) >= 2:
        skill = skills[0]
        questions.append({
            "id": 4,
            "question": f"I notice you have experience with {skill}. Can you explain how you've applied it in your work and describe a specific use case?",
            "category": "resume_based",
            "difficulty": "medium",
            "focus_area": skill,
            "follow_up": False,
            "expected_duration_seconds": 120
        })
        
        skill2 = skills[1]
        questions.append({
            "id": 5,
            "question": f"How have you used {skill2} alongside other technologies in your projects? Any integration challenges?",
            "category": "follow_up",
            "difficulty": "medium",
            "focus_area": skill2,
            "follow_up": True,
            "expected_duration_seconds": 120
        })
    else:
        questions.append({
            "id": 4,
            "question": "Which technology or tool are you most proficient in? How have you applied it in real-world scenarios?",
            "category": "resume_based",
            "difficulty": "medium",
            "focus_area": "technical_skills",
            "follow_up": False,
            "expected_duration_seconds": 120
        })
        
        questions.append({
            "id": 5,
            "question": "Can you walk me through how you keep your technical skills up to date?",
            "category": "follow_up",
            "difficulty": "easy",
            "focus_area": "learning",
            "follow_up": True,
            "expected_duration_seconds": 90
        })
    
    # ═══════════════════════════════════════════════════════════════
    # SECTION 3: ROLE-BASED TECHNICAL (Questions 6-9)
    # ═══════════════════════════════════════════════════════════════
    role_questions = get_role_based_questions(target_role, experience_level)
    for i, rq in enumerate(role_questions[:4]):
        rq["id"] = 6 + i
        questions.append(rq)
    
    # ═══════════════════════════════════════════════════════════════
    # SECTION 4: BEHAVIORAL (Questions 10-12)
    # ═══════════════════════════════════════════════════════════════
    behavioral_questions = [
        {
            "id": 10,
            "question": "Tell me about a time when you had to collaborate closely with a team to deliver a project. What was your approach?",
            "category": "behavioral",
            "difficulty": "medium",
            "focus_area": "teamwork",
            "follow_up": False,
            "expected_duration_seconds": 120
        },
        {
            "id": 11,
            "question": "Describe a situation where you faced a tight deadline or conflicting priorities. How did you handle the pressure?",
            "category": "behavioral",
            "difficulty": "medium",
            "focus_area": "pressure_handling",
            "follow_up": False,
            "expected_duration_seconds": 120
        },
        {
            "id": 12,
            "question": f"Why are you interested in this {target_role} position, and where do you see yourself growing in the next few years?",
            "category": "behavioral",
            "difficulty": "easy",
            "focus_area": "career_goals",
            "follow_up": False,
            "expected_duration_seconds": 90
        }
    ]
    questions.extend(behavioral_questions)
    
    return questions[:12]


def get_role_based_questions(target_role: str, experience_level: str) -> List[Dict[str, Any]]:
    """
    Get role-specific technical questions based on target role.
    """
    role_lower = target_role.lower()
    
    # Default technical questions
    default_questions = [
        {
            "question": f"What do you consider the most important skills for a {target_role}? How do you embody them?",
            "category": "role_based",
            "difficulty": "medium",
            "focus_area": "role_understanding",
            "follow_up": False,
            "expected_duration_seconds": 120
        },
        {
            "question": "How do you approach debugging a complex issue in production? Walk me through your process.",
            "category": "role_based",
            "difficulty": "medium",
            "focus_area": "problem_solving",
            "follow_up": False,
            "expected_duration_seconds": 150
        },
        {
            "question": "If you were to design a system from scratch for a specific use case, what factors would you consider first?",
            "category": "role_based",
            "difficulty": "hard",
            "focus_area": "system_design",
            "follow_up": False,
            "expected_duration_seconds": 180
        },
        {
            "question": "How do you ensure code quality and maintainability in your projects?",
            "category": "role_based",
            "difficulty": "medium",
            "focus_area": "best_practices",
            "follow_up": False,
            "expected_duration_seconds": 120
        }
    ]
    
    # Role-specific question banks
    if "frontend" in role_lower or "react" in role_lower or "ui" in role_lower:
        return [
            {
                "question": "Explain the concept of virtual DOM and how React uses it for performance optimization.",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "react_fundamentals",
                "follow_up": False,
                "expected_duration_seconds": 120
            },
            {
                "question": "How do you handle state management in large React applications? Compare different approaches you've used.",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "state_management",
                "follow_up": False,
                "expected_duration_seconds": 150
            },
            {
                "question": "Walk me through how you would optimize a slow-loading React application.",
                "category": "role_based",
                "difficulty": "hard",
                "focus_area": "performance",
                "follow_up": False,
                "expected_duration_seconds": 180
            },
            {
                "question": "How do you approach responsive design and accessibility in your frontend work?",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "accessibility",
                "follow_up": False,
                "expected_duration_seconds": 120
            }
        ]
    
    elif "backend" in role_lower or "api" in role_lower or "server" in role_lower:
        return [
            {
                "question": "Explain how you would design a RESTful API for a complex domain. What principles do you follow?",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "api_design",
                "follow_up": False,
                "expected_duration_seconds": 150
            },
            {
                "question": "How do you handle database optimization? Describe your approach to query optimization and indexing.",
                "category": "role_based",
                "difficulty": "hard",
                "focus_area": "database",
                "follow_up": False,
                "expected_duration_seconds": 150
            },
            {
                "question": "Walk me through how you would implement authentication and authorization in a microservices architecture.",
                "category": "role_based",
                "difficulty": "hard",
                "focus_area": "security",
                "follow_up": False,
                "expected_duration_seconds": 180
            },
            {
                "question": "How do you approach error handling and logging in production systems?",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "reliability",
                "follow_up": False,
                "expected_duration_seconds": 120
            }
        ]
    
    elif "fullstack" in role_lower or "full stack" in role_lower or "full-stack" in role_lower:
        return [
            {
                "question": "How do you decide when to handle logic on the frontend vs. the backend?",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "architecture",
                "follow_up": False,
                "expected_duration_seconds": 120
            },
            {
                "question": "Describe how you would implement real-time features like live updates or chat in a full-stack application.",
                "category": "role_based",
                "difficulty": "hard",
                "focus_area": "real_time",
                "follow_up": False,
                "expected_duration_seconds": 180
            },
            {
                "question": "How do you manage deployments and CI/CD for a full-stack application?",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "devops",
                "follow_up": False,
                "expected_duration_seconds": 150
            },
            {
                "question": "What's your approach to testing across the stack - frontend, backend, and integration?",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "testing",
                "follow_up": False,
                "expected_duration_seconds": 120
            }
        ]
    
    elif "data" in role_lower or "ml" in role_lower or "machine learning" in role_lower or "ai" in role_lower:
        return [
            {
                "question": "Explain the difference between supervised and unsupervised learning with real-world examples.",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "ml_fundamentals",
                "follow_up": False,
                "expected_duration_seconds": 150
            },
            {
                "question": "How do you handle overfitting in machine learning models? What techniques have you used?",
                "category": "role_based",
                "difficulty": "hard",
                "focus_area": "model_optimization",
                "follow_up": False,
                "expected_duration_seconds": 150
            },
            {
                "question": "Walk me through your approach to feature engineering and data preprocessing.",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "data_preparation",
                "follow_up": False,
                "expected_duration_seconds": 180
            },
            {
                "question": "How do you deploy and monitor ML models in production?",
                "category": "role_based",
                "difficulty": "hard",
                "focus_area": "mlops",
                "follow_up": False,
                "expected_duration_seconds": 150
            }
        ]
    
    elif "devops" in role_lower or "sre" in role_lower or "cloud" in role_lower:
        return [
            {
                "question": "Explain your approach to infrastructure as code. What tools have you used?",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "iac",
                "follow_up": False,
                "expected_duration_seconds": 150
            },
            {
                "question": "How would you design a CI/CD pipeline for a microservices architecture?",
                "category": "role_based",
                "difficulty": "hard",
                "focus_area": "cicd",
                "follow_up": False,
                "expected_duration_seconds": 180
            },
            {
                "question": "Describe how you approach monitoring and alerting in production systems.",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "observability",
                "follow_up": False,
                "expected_duration_seconds": 150
            },
            {
                "question": "How do you handle secrets management and security in cloud environments?",
                "category": "role_based",
                "difficulty": "hard",
                "focus_area": "security",
                "follow_up": False,
                "expected_duration_seconds": 120
            }
        ]
    
    # Python/Django/Flask
    elif "python" in role_lower or "django" in role_lower or "flask" in role_lower:
        return [
            {
                "question": "Explain the difference between lists and tuples in Python and when you'd use each.",
                "category": "role_based",
                "difficulty": "easy",
                "focus_area": "python_basics",
                "follow_up": False,
                "expected_duration_seconds": 90
            },
            {
                "question": "How do decorators work in Python? Can you give an example of when you've used them?",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "python_advanced",
                "follow_up": False,
                "expected_duration_seconds": 150
            },
            {
                "question": "How do you handle async operations in Python? Compare different approaches.",
                "category": "role_based",
                "difficulty": "hard",
                "focus_area": "async",
                "follow_up": False,
                "expected_duration_seconds": 150
            },
            {
                "question": "What best practices do you follow for writing maintainable Python code?",
                "category": "role_based",
                "difficulty": "medium",
                "focus_area": "best_practices",
                "follow_up": False,
                "expected_duration_seconds": 120
            }
        ]
    
    return default_questions
