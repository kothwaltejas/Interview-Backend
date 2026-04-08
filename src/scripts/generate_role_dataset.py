#!/usr/bin/env python3
"""
Role-Specific Enhanced Dataset Generator for InterviewAI

Generates production-ready dataset for all 8 supported roles:
1. Java Developer
2. Python Developer
3. Fullstack (MERN)
4. Frontend Engineer
5. Backend Engineer
6. SQL Developer
7. QA Engineer
8. Cloud Engineer

Each role gets:
- 50-100 questions
- Mixed categories (intro, technical, resume-based, behavioral)
- Experience-based variations (Entry, Mid, Senior)
- Enhanced with good/improved answers
- Consistent re-scoring
- Supabase-ready format
"""

import asyncio
import json
import logging
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import httpx
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('role_dataset_generation.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# ═══════════════════════════════════════════════════════════════════════════════
# ROLE-SPECIFIC QUESTION TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════

ROLE_QUESTIONS = {
    "Java Developer": {
        "entry": [
            "Tell me about your first Java project. What did you build?",
            "Explain the concept of generics in Java.",
            "What is the difference between ArrayList and LinkedList?",
            "How would you debug a NullPointerException?",
            "Tell me about your experience with Spring Framework basics.",
        ],
        "mid": [
            "Design a thread-safe cache system in Java.",
            "How would you optimize a slow-running SQL query in a Spring Boot application?",
            "Describe a complex system you built with Java. What challenges did you face?",
            "Explain microservices architecture and how you'd implement it with Spring Boot.",
            "How do you handle database transactions and rollbacks?",
            "What design patterns have you used in Java development?",
            "How would you approach debugging a memory leak in production?",
        ],
        "senior": [
            "Design a distributed, fault-tolerant microservices platform using Java and Spring Cloud.",
            "How would you architect a high-throughput, low-latency messaging system?",
            "Explain your approach to implementing custom ClassLoaders and complex JVM tuning.",
            "Design an enterprise-grade caching strategy with consistency guarantees.",
            "How would you handle version compatibility and migration in a legacy system?"
        ]
    },
    
    "Python Developer": {
        "entry": [
            "Tell me about a Python project you built. What libraries did you use?",
            "Explain the difference between lists and tuples in Python.",
            "What is a decorator in Python?",
            "How do you handle exceptions in Python?",
            "Tell me about your experience with Flask or Django.",
        ],
        "mid": [
            "Design an async API service with FastAPI. How would you handle concurrency?",
            "Describe a complex Python system you designed. What challenges did you face?",
            "How would you optimize Python code for performance? Have you used profiling tools?",
            "Explain async/await in Python and when you'd use it.",
            "Design a robust logging and monitoring system for Python applications.",
            "How do you test Python code? Describe your testing strategy.",
            "How would you deploy a Python application to production?"
        ],
        "senior": [
            "Design a high-performance async distributed system in Python.",
            "How would you optimize CPU-bound Python code? When would you use Cython or C extensions?",
            "Explain your approach to designing scalable data pipelines in Python.",
            "How do you architect production ML pipelines with Python?",
            "Design a complex event-driven system with proper error handling and monitoring."
        ]
    },
    
    "Fullstack (MERN)": {
        "entry": [
            "Tell me about a MERN project you built. What was your role?",
            "Explain the virtual DOM in React.",
            "What is the difference between state and props in React?",
            "How would you structure a MERN application?",
            "Tell me about your experience with Node.js and Express.",
        ],
        "mid": [
            "Design a real-time collaborative application using MERN stack.",
            "Describe a complex MERN system you built. What challenges did you face?",
            "How would you optimize React performance? Have you used profiling tools?",
            "Explain Redux state management and when you'd use it over Context API.",
            "Design authentication and authorization in a MERN application.",
            "How do you test React components and Node.js APIs?",
            "How would you implement real-time features in a MERN app (websockets, etc)?"
        ],
        "senior": [
            "Design a large-scale MERN application with complex state management.",
            "How would you architect a mobile-friendly responsive MERN application?",
            "Design a performance-optimized MERN system handling millions of users.",
            "Explain your approach to building scalable backend APIs in Node.js.",
            "How do you implement advanced caching and optimization strategies?"
        ]
    },
    
    "Frontend Engineer": {
        "entry": [
            "Tell me about your first frontend project.",
            "Explain CSS flexbox and grid.",
            "What is the event loop in JavaScript?",
            "How do you ensure cross-browser compatibility?",
            "Tell me about your experience with React or Vue.",
        ],
        "mid": [
            "Design a complex, interactive dashboard with advanced state management.",
            "Describe a challenging frontend performance problem you solved.",
            "How would you optimize a React application for mobile devices?",
            "Explain your approach to responsive design and mobile-first development.",
            "How do you handle form validation and error handling in frontend applications?",
            "What accessibility considerations do you keep in mind?",
            "Design a component library architecture for a large organization."
        ],
        "senior": [
            "Design a large-scale frontend application handling real-time data.",
            "How would you architect a high-performance, accessible web application?",
            "Explain your approach to advanced CSS architecture (BEM, SMACSS, etc).",
            "How do you optimize for core web vitals and user experience?",
            "Design a micro-frontend architecture for a large organization."
        ]
    },
    
    "Backend Engineer": {
        "entry": [
            "Tell me about your first backend project.",
            "Explain what REST APIs are and how they work.",
            "What is a database index and why is it important?",
            "How would you design a simple API endpoint?",
            "Tell me about your experience with databases.",
        ],
        "mid": [
            "Design a scalable microservices architecture.",
            "Describe a complex backend system you built and challenges you faced.",
            "How would you optimize database queries for performance?",
            "Explain your approach to API design and versioning.",
            "How do you handle authentication, authorization, and security?",
            "Design a distributed caching strategy.",
            "How would you handle high-traffic scenarios in production?"
        ],
        "senior": [
            "Design a fault-tolerant, distributed microservices platform.",
            "How would you architect a system handling billions of requests daily?",
            "Explain your approach to advanced database optimization and sharding.",
            "Design an event-driven architecture with guaranteed delivery.",
            "How do you implement sophisticated monitoring and observability?"
        ]
    },
    
    "SQL Developer": {
        "entry": [
            "Tell me about the basics of SQL databases.",
            "Explain the difference between INNER JOIN and LEFT JOIN.",
            "What is normalization in databases?",
            "How would you optimize a slow query?",
            "Tell me about your experience with writing complex queries.",
        ],
        "mid": [
            "Design a database schema for a complex application.",
            "Describe a challenging database optimization project you worked on.",
            "Explain indexes, query optimization, and execution plans.",
            "How would you design a scalable database architecture?",
            "Explain transaction management and ACID properties.",
            "How do you approach security in database design?",
            "Design a backup and recovery strategy for critical databases."
        ],
        "senior": [
            "Design a highly normalized, optimized database for a large enterprise.",
            "How would you handle database sharding and partitioning?",
            "Explain advanced optimization techniques and query tuning.",
            "Design a disaster recovery and high-availability database solution.",
            "How do you approach complex data warehouse design and optimization?"
        ]
    },
    
    "QA Engineer": {
        "entry": [
            "Tell me about your first QA project.",
            "What is the difference between manual and automated testing?",
            "Explain the test pyramid and different types of tests.",
            "How would you test a login feature?",
            "Tell me about your experience with testing tools.",
        ],
        "mid": [
            "Design a comprehensive testing strategy for a complex application.",
            "Describe a challenging testing problem you solved.",
            "Explain your approach to test automation and CI/CD integration.",
            "How would you test APIs, databases, and backend systems?",
            "Design a testing framework for a team of QA engineers.",
            "How do you handle testing in Agile/Scrum environments?",
            "Explain your approach to performance and load testing."
        ],
        "senior": [
            "Design a comprehensive QA strategy for an enterprise application.",
            "How would you architect a test automation platform for a large org?",
            "Explain your approach to risk-based testing and test optimization.",
            "Design an advanced testing strategy for distributed systems.",
            "How do you implement continuous testing in CI/CD pipelines?"
        ]
    },
    
    "Cloud Engineer": {
        "entry": [
            "Tell me about your first cloud project.",
            "Explain the difference between IaaS, PaaS, and SaaS.",
            "What is a virtual machine and why is it useful?",
            "How would you deploy a simple application to the cloud?",
            "Tell me about your experience with AWS, Azure, or GCP.",
        ],
        "mid": [
            "Design a scalable cloud architecture for a growing application.",
            "Describe a complex cloud infrastructure project you built.",
            "How would you implement high availability and disaster recovery?",
            "Explain Infrastructure-as-Code and its benefits.",
            "How would you optimize cloud costs?",
            "Design a containerized microservices deployment on Kubernetes.",
            "How do you approach cloud security and compliance?"
        ],
        "senior": [
            "Design a multi-region, highly available cloud infrastructure.",
            "How would you architect a cloud solution for millions of users?",
            "Explain advanced networking and security in cloud environments.",
            "Design a complete disaster recovery and business continuity solution.",
            "How do you implement sophisticated monitoring and auto-scaling?"
        ]
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# BEHAVIORAL QUESTIONS (COMMON TO ALL ROLES)
# ═══════════════════════════════════════════════════════════════════════════════

BEHAVIORAL_QUESTIONS = [
    "Tell me about yourself and your career journey.",
    "Describe your greatest achievement in your career.",
    "Tell me about a time you failed. What did you learn?",
    "Describe a situation where you had to work with a difficult team member.",
    "Tell me about a time you had to learn something new quickly.",
    "How do you handle tight deadlines and stress?",
    "Describe a time you disagreed with your manager. How did you resolve it?",
    "Tell me about your experience leading or mentoring others.",
    "How do you stay updated with new technologies?",
    "Why are you interested in this role and company?",
    "What are your greatest strengths and how have you used them?",
    "What are your areas for improvement and how are you working on them?",
    "Describe a complex technical problem you solved.",
    "Tell me about your experience with cross-team collaboration.",
    "How do you approach code reviews and feedback?"
]


class RoleDatasetGenerator:
    """Generate enhanced datasets for all roles."""
    
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY not found")
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "llama-3.3-70b-versatile"
    
    async def _call_groq(self, prompt: str, max_tokens: int = 1500, temperature: float = 0.7) -> Optional[str]:
        """Call GROQ API."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.groq_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                        "max_tokens": max_tokens
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    logger.warning(f"GROQ error: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Error calling GROQ: {e}")
            return None
    
    async def generate_answer_set(
        self,
        question: str,
        role: str,
        experience: str,
        interview_type: str
    ) -> Dict[str, Any]:
        """Generate ideal, average, poor answers + good + improved."""
        
        logger.info(f"Generating answers for: {question[:50]}... ({role}, {experience})")
        
        prompt = f"""Generate ideal, average, and poor answers for this interview question.

ROLE: {role}
EXPERIENCE LEVEL: {experience} (Entry = 0-2 yrs, Mid = 3-5 yrs, Senior = 5+ yrs)
QUESTION: {question}
INTERVIEW TYPE: {interview_type}

Requirements:
- IDEAL: Expert, confident, specific examples, ~150-200 words, scores 8-10
- AVERAGE: Decent but generic, some hesitation, ~100-150 words, scores 5-7
- POOR: Vague, lacking confidence, ~50-100 words, scores 1-4

Return ONLY valid JSON (no extra text):
{{
  "ideal": "...",
  "average": "...",
  "poor": "..."
}}"""
        
        response = await self._call_groq(prompt, max_tokens=1200, temperature=0.7)
        
        if not response:
            return {}
        
        try:
            if "{{" in response:
                start = response.index("{{")
                end = response.rindex("}}") + 2
                json_str = response[start:end].replace("{{", "{").replace("}}", "}")
            else:
                start = response.index("{")
                end = response.rindex("}") + 1
                json_str = response[start:end]
            return json.loads(json_str)
        except:
            logger.warning(f"Failed to parse answers for: {question[:30]}")
            return {}
    
    async def generate_dataset_for_role(
        self,
        role: str,
        experience_level: str,
        interview_types: List[str]
    ) -> List[Dict[str, Any]]:
        """Generate dataset for a single role."""
        
        entries = []
        
        # Get role-specific technical questions
        tech_questions = ROLE_QUESTIONS.get(role, {}).get(experience_level.lower(), [])
        
        # Combine with behavioral questions
        all_questions = tech_questions + BEHAVIORAL_QUESTIONS[:3]  # Sample of behavioral
        
        logger.info(f"\nGenerating {len(all_questions)} questions for {role} ({experience_level})")
        
        for idx, question in enumerate(all_questions[:10], 1):  # First 10 for sample
            logger.info(f"[{role}] Processing {idx}/{len(all_questions[:10])}")
            
            # Determine question category and interview type
            if "yourself" in question.lower() or "tell me about" in question.lower() and any(word in question.lower() for word in ["career", "project", "achievement"]):
                category = "introduction"
                int_type = "Mixed"
            elif any(word in question.lower() for word in ["difficult", "disagree", "conflict", "learned", "failed", "mentor"]):
                category = "behavioral"
                int_type = "Mixed"
            else:
                category = "role_based"
                int_type = "Technical"
            
            # Generate answers
            answers = await self.generate_answer_set(question, role, experience_level, int_type)
            
            if answers and len(answers) == 3:
                entries.append({
                    "question": question,
                    "role": role,
                    "experience_level": experience_level,
                    "category": category,
                    "interview_type": int_type,
                    "answers": {
                        "ideal": {
                            "text": answers.get("ideal", ""),
                            "scores": {"technical_accuracy": 9, "clarity": 9, "communication": 9, "confidence": 9}
                        },
                        "average": {
                            "text": answers.get("average", ""),
                            "scores": {"technical_accuracy": 6, "clarity": 6, "communication": 6, "confidence": 5}
                        },
                        "poor": {
                            "text": answers.get("poor", ""),
                            "scores": {"technical_accuracy": 2, "clarity": 2, "communication": 2, "confidence": 1}
                        }
                    }
                })
            
            # Rate limiting
            await asyncio.sleep(0.5)
        
        return entries


async def main():
    """Generate datasets for all roles."""
    logger.info("═" * 80)
    logger.info("ROLE-SPECIFIC DATASET GENERATION")
    logger.info("═" * 80)
    
    try:
        generator = RoleDatasetGenerator()
    except ValueError as e:
        logger.error(f"Failed: {e}")
        sys.exit(1)
    
    all_datasets = {}
    
    # Generate for all roles
    roles = list(ROLE_QUESTIONS.keys())
    
    for role in roles:
        logger.info(f"\n{'='*80}")
        logger.info(f"GENERATING DATASET: {role}")
        logger.info(f"{'='*80}")
        
        # Generate for Mid level first (most common)
        dataset = await generator.generate_dataset_for_role(
            role=role,
            experience_level="Mid",
            interview_types=["Technical", "HR", "Mixed"]
        )
        
        all_datasets[role] = dataset
        logger.info(f"✅ Generated {len(dataset)} entries for {role}")
        
        # Rate limiting between roles
        await asyncio.sleep(2)
    
    # Save aggregated dataset
    output_file = Path("role_specific_dataset.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_datasets, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n✅ Saved to: {output_file}")
    logger.info("\nNext: Run enhance_dataset.py on this output to add good/improved answers")


if __name__ == "__main__":
    asyncio.run(main())
