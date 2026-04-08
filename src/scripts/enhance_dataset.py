#!/usr/bin/env python3
"""
Production-Grade Dataset Enhancement Pipeline for InterviewAI

Enhances dataset with:
1. Validation & cleaning
2. Normalization
3. Data enrichment (good + improved answers)
4. Re-scoring with consistency
5. Metadata generation (difficulty, category, time estimates)
6. Output compatible with Supabase schema

Input: existing dataset.json OR raw generation
Output: enhanced_dataset.json (10 entries first for review)
"""

import asyncio
import json
import logging
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging with UTF-8
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dataset_enhancement.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

SUPPORTED_ROLES = [
    "Java Developer",
    "Python Developer",
    "Fullstack (MERN)",
    "Frontend Engineer",
    "Backend Engineer",
    "SQL Developer",
    "QA Engineer",
    "Cloud Engineer"
]

QUESTION_CATEGORIES = [
    "introduction",
    "resume_based",
    "role_based",
    "behavioral",
    "follow_up",
]

DIFFICULTIES = ["easy", "medium", "hard"]

# Role-specific technical keywords for validation
ROLE_KEYWORDS = {
    "Java Developer": ["Java", "Spring", "Hibernate", "JVM", "Maven", "Microservices"],
    "Python Developer": ["Python", "Django", "FastAPI", "Async", "Flask", "Testing"],
    "Fullstack (MERN)": ["React", "Node", "MongoDB", "Express", "JavaScript", "REST API"],
    "Frontend Engineer": ["React", "Vue", "Angular", "CSS", "DOM", "Performance", "Accessibility"],
    "Backend Engineer": ["API", "Database", "Scalability", "Load Balancing", "Caching", "Architecture"],
    "SQL Developer": ["SQL", "Database Design", "Optimization", "Query", "Index", "Transaction"],
    "QA Engineer": ["Testing", "Automation", "Bug", "Test Cases", "Selenium", "Quality Assurance"],
    "Cloud Engineer": ["AWS", "Azure", "GCP", "Infrastructure", "Kubernetes", "Deployment"]
}


@dataclass
class AnswerData:
    """Represents a single answer with scores."""
    text: str
    scores: Dict[str, int]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EnhancedDatasetEntry:
    """Production-ready dataset entry."""
    question: str
    difficulty: str  # easy, medium, hard
    category: str     # intro, resume_based, role_based, behavioral
    target_role: str  # One of SUPPORTED_ROLES
    experience_level: str  # Entry, Mid, Senior
    interview_type: str  # Technical, HR, Mixed
    expected_answer_time_seconds: int  # Rough estimate
    key_points_expected: List[str]  # 4-8 bullet points
    answers: Dict[str, Optional[AnswerData]]  # ideal, good, average, poor, improved
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "difficulty": self.difficulty,
            "category": self.category,
            "target_role": self.target_role,
            "experience_level": self.experience_level,
            "interview_type": self.interview_type,
            "expected_answer_time_seconds": self.expected_answer_time_seconds,
            "key_points_expected": self.key_points_expected,
            "answers": {
                level: answer.to_dict() if answer else None
                for level, answer in self.answers.items()
            }
        }


class DatasetEnhancer:
    """Main enhancement pipeline."""
    
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY not found in environment")
        
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "llama-3.3-70b-versatile"
        self.max_retries = 3
        self.batch_size = 10
        
        # Statistics tracking
        self.stats = {
            "total_processed": 0,
            "cleaned": 0,
            "enriched": 0,
            "skipped": 0,
            "validation_passed": 0
        }
    
    async def _call_groq(
        self, 
        prompt: str, 
        max_tokens: int = 2000,
        temperature: float = 0.7,
        retry_count: int = 0
    ) -> Optional[str]:
        """Call GROQ API with retry logic."""
        if retry_count >= self.max_retries:
            return None
        
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
                    logger.warning(f"GROQ API error: {response.status_code}, retrying...")
                    await asyncio.sleep(2 ** retry_count)
                    return await self._call_groq(prompt, max_tokens, temperature, retry_count + 1)
        
        except Exception as e:
            logger.error(f"Error calling GROQ: {e}, retry attempt {retry_count + 1}")
            await asyncio.sleep(2 ** retry_count)
            return await self._call_groq(prompt, max_tokens, temperature, retry_count + 1)
    
    def _validate_entry(self, entry: Dict[str, Any]) -> bool:
        """Validate entry structure."""
        if not isinstance(entry, dict):
            return False
        
        # Check required fields
        if "question" not in entry or not entry["question"]:
            return False
        
        if "answers" not in entry or not isinstance(entry["answers"], dict):
            return False
        
        # Check for required answer types
        required_answers = ["ideal", "average", "poor"]
        for answer_type in required_answers:
            if answer_type not in entry["answers"] or entry["answers"][answer_type] is None:
                return False
            
            answer = entry["answers"][answer_type]
            if not isinstance(answer, dict):
                return False
            
            if "text" not in answer or not answer["text"]:
                return False
            
            if "scores" not in answer or not isinstance(answer["scores"], dict):
                return False
            
            # Validate score structure
            required_scores = ["technical_accuracy", "clarity", "communication", "confidence"]
            for score_key in required_scores:
                if score_key not in answer["scores"]:
                    return False
                
                score_val = answer["scores"][score_key]
                if not isinstance(score_val, (int, float)) or not (1 <= score_val <= 10):
                    return False
        
        return True
    
    def _normalize_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize entry text and scores."""
        normalized = entry.copy()
        
        # Normalize question
        normalized["question"] = normalized["question"].strip()
        
        # Normalize answers
        for level in ["ideal", "average", "poor"]:
            if level in normalized["answers"] and normalized["answers"][level]:
                answer = normalized["answers"][level]
                
                # Trim whitespace
                answer["text"] = answer["text"].strip()
                
                # Ensure scores are ints in valid range
                for score_key in ["technical_accuracy", "clarity", "communication", "confidence"]:
                    if score_key in answer["scores"]:
                        val = int(answer["scores"][score_key])
                        answer["scores"][score_key] = max(1, min(10, val))
        
        return normalized
    
    async def _generate_good_answer(self, question: str, ideal_answer: str, target_role: str) -> Optional[str]:
        """Generate 'good' answer (between ideal and average)."""
        prompt = f"""Generate a "good" quality answer to this interview question for a {target_role} role.

QUESTION: {question}

REFERENCE (Ideal Answer): {ideal_answer[:200]}...

REQUIREMENTS:
- Quality between ideal (9) and average (7)
- Natural, realistic, slightly less polished than ideal
- Shows solid understanding but not perfect
- ~100-150 words
- Avoid being too perfect or scripted

ANSWER (ONLY return the answer text, no labels or extra text):"""
        
        response = await self._call_groq(prompt, max_tokens=300, temperature=0.7)
        return response.strip() if response else None
    
    async def _generate_improved_answer(self, question: str, poor_or_avg_answer: str, target_role: str) -> Optional[str]:
        """Rewrite poor/average answer into improved, high-quality version."""
        prompt = f"""Rewrite and improve this interview answer. Transform it into a high-quality, structured response.

QUESTION: {question}

ORIGINAL ANSWER: {poor_or_avg_answer}

REQUIREMENTS:
- Rewrite into perfect, structured, high-quality answer
- Show clear understanding and confidence
- Use professional language
- Include specific examples if applicable
- ~150-200 words
- This should be clearly better than the original

IMPROVED ANSWER (ONLY return the answer text, no labels or extra text):"""
        
        response = await self._call_groq(prompt, max_tokens=400, temperature=0.5)
        return response.strip() if response else None
    
    async def _generate_key_points(self, question: str, ideal_answer: str) -> Optional[List[str]]:
        """Generate 4-8 key points expected in ideal answer."""
        prompt = f"""Extract the 4-8 most important points/concepts that should be in a good answer to this question.

QUESTION: {question}

REFERENCE ANSWER: {ideal_answer}

REQUIREMENTS:
- Return 4-8 bullet points
- Each point should be a key concept or speaking point
- Format as JSON array of strings
- Be specific and actionable

JSON OUTPUT (ONLY JSON, no other text):"""
        
        response = await self._call_groq(prompt, max_tokens=300, temperature=0.3)
        
        if not response:
            return None
        
        try:
            # Try to extract JSON array
            if "[" in response and "]" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                json_str = response[start:end]
                return json.loads(json_str)
        except:
            pass
        
        return None
    
    async def _rescore_answers(self, question: str, answers: Dict[str, str], target_role: str) -> Dict[str, Any]:
        """Re-score all answers with consistent LLM evaluation."""
        answers_text = "\n\n".join([
            f"{level.upper()}:\n{text}" 
            for level, text in answers.items() if text
        ])
        
        prompt = f"""Score these interview answers on 4 criteria.

QUESTION: {question}
TARGET ROLE: {target_role}

ANSWERS TO SCORE:
{answers_text}

SCORING RULES:
- IDEAL should score 8-10 (excellent, confident, well-structured)
- GOOD should score 7-8 (solid, good understanding)
- AVERAGE should score 5-7 (acceptable, some hesitation)
- POOR should score 1-4 (weak, unclear, lacks confidence)
- Strict ordering: IDEAL > GOOD > AVERAGE > POOR

Score on these criteria (1-10 each):
1. technical_accuracy: How technically correct and accurate
2. clarity: How clear and well-explained
3. communication: How well-expressed and structured
4. confidence: Level of confidence demonstrated

Return ONLY valid JSON in this format (no extra text):
{{
  "ideal": {{
    "technical_accuracy": int,
    "clarity": int,
    "communication": int,
    "confidence": int
  }},
  "good": {{
    "technical_accuracy": int,
    "clarity": int,
    "communication": int,
    "confidence": int
  }},
  "average": {{
    "technical_accuracy": int,
    "clarity": int,
    "communication": int,
    "confidence": int
  }},
  "poor": {{
    "technical_accuracy": int,
    "clarity": int,
    "communication": int,
    "confidence": int
  }}
}}"""
        
        response = await self._call_groq(prompt, max_tokens=600, temperature=0.2)
        
        if not response:
            return {}
        
        try:
            # Extract JSON
            if "{" in response and "}" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                json_str = response[start:end]
                return json.loads(json_str)
        except:
            logger.warning(f"Failed to parse rescore response: {response[:100]}")
            return {}
        
        return {}
    
    async def _get_metadata(self, question: str, category: str, target_role: str) -> Dict[str, Any]:
        """Determine difficulty, expected time, and refine category."""
        prompt = f"""Analyze this interview question and return metadata.

QUESTION: {question}
CATEGORY: {category}
TARGET ROLE: {target_role}

Determine:
1. difficulty: "easy" (basic concepts), "medium" (applied knowledge), "hard" (deep/system design)
2. expected_answer_time_seconds: Rough time to answer (30-120)

Return ONLY JSON (no extra text):
{{
  "difficulty": "easy|medium|hard",
  "expected_answer_time_seconds": int
}}"""
        
        response = await self._call_groq(prompt, max_tokens=100, temperature=0.2)
        
        if not response:
            return {"difficulty": "medium", "expected_answer_time_seconds": 60}
        
        try:
            if "{" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                json_str = response[start:end]
                return json.loads(json_str)
        except:
            pass
        
        return {"difficulty": "medium", "expected_answer_time_seconds": 60}
    
    async def _enhance_entry(
        self, 
        entry: Dict[str, Any],
        target_role: str = "Backend Engineer",
        experience_level: str = "Mid",
        interview_type: str = "Mixed"
    ) -> Optional[EnhancedDatasetEntry]:
        """Enhance a single dataset entry."""
        
        # Validate
        if not self._validate_entry(entry):
            logger.warning(f"Entry validation failed: {entry.get('question', '')[:50]}")
            self.stats["skipped"] += 1
            return None
        
        # Normalize
        normalized = self._normalize_entry(entry)
        self.stats["cleaned"] += 1
        
        question = normalized["question"]
        ideal_text = normalized["answers"]["ideal"]["text"]
        average_text = normalized["answers"]["average"]["text"]
        poor_text = normalized["answers"]["poor"]["text"]
        
        # Generate "good" answer
        logger.info(f"Generating good answer: {question[:50]}...")
        good_text = await self._generate_good_answer(question, ideal_text, target_role)
        
        if not good_text:
            logger.warning(f"Failed to generate good answer for: {question[:50]}")
            good_text = average_text  # Fallback
        
        # Generate "improved" answer
        logger.info(f"Generating improved answer: {question[:50]}...")
        improved_text = await self._generate_improved_answer(question, poor_text, target_role)
        
        if not improved_text:
            logger.warning(f"Failed to generate improved answer for: {question[:50]}")
            improved_text = ideal_text  # Fallback
        
        # Generate key points
        logger.info(f"Extracting key points: {question[:50]}...")
        key_points = await self._generate_key_points(question, ideal_text)
        
        if not key_points or len(key_points) == 0:
            key_points = [
                "Demonstrates core technical knowledge",
                "Shows practical experience",
                "Addresses challenges thoughtfully",
                "Communicates clearly"
            ]
        
        # Re-score answers
        logger.info(f"Re-scoring answers: {question[:50]}...")
        rescores = await self._rescore_answers(
            question,
            {
                "ideal": ideal_text,
                "good": good_text,
                "average": average_text,
                "poor": poor_text
            },
            target_role
        )
        
        # Get metadata
        category = normalized.get("question_metadata", {}).get("category", "role_based")
        metadata = await self._get_metadata(question, category, target_role)
        
        # Determine category
        category = "introduction" if "tell me about yourself" in question.lower() else "role_based"
        
        # Build enhanced entry
        enhanced = EnhancedDatasetEntry(
            question=question,
            difficulty=metadata.get("difficulty", "medium"),
            category=category,
            target_role=target_role,
            experience_level=experience_level,
            interview_type=interview_type,
            expected_answer_time_seconds=metadata.get("expected_answer_time_seconds", 60),
            key_points_expected=key_points,
            answers={
                "ideal": AnswerData(
                    text=ideal_text,
                    scores=rescores.get("ideal", normalized["answers"]["ideal"]["scores"])
                ),
                "good": AnswerData(
                    text=good_text,
                    scores=rescores.get("good", {
                        "technical_accuracy": 7,
                        "clarity": 7,
                        "communication": 7,
                        "confidence": 7
                    })
                ),
                "average": AnswerData(
                    text=average_text,
                    scores=rescores.get("average", normalized["answers"]["average"]["scores"])
                ),
                "poor": AnswerData(
                    text=poor_text,
                    scores=rescores.get("poor", normalized["answers"]["poor"]["scores"])
                ),
                "improved": AnswerData(
                    text=improved_text,
                    scores={"technical_accuracy": 9, "clarity": 9, "communication": 9, "confidence": 9}
                )
            }
        )
        
        self.stats["enriched"] += 1
        return enhanced
    
    async def enhance_dataset(
        self,
        entries: List[Dict[str, Any]],
        target_role: str = "Backend Engineer",
        experience_level: str = "Mid",
        interview_type: str = "Mixed"
    ) -> List[EnhancedDatasetEntry]:
        """Enhance multiple entries with batch processing."""
        enhanced_entries = []
        
        total = len(entries)
        for i, entry in enumerate(entries):
            logger.info(f"Processing entry {i+1}/{total}...")
            
            enhanced = await self._enhance_entry(
                entry,
                target_role=target_role,
                experience_level=experience_level,
                interview_type=interview_type
            )
            
            if enhanced:
                enhanced_entries.append(enhanced)
            
            # Rate limiting
            if (i + 1) % self.batch_size == 0:
                await asyncio.sleep(1)
        
        return enhanced_entries


async def main():
    """Main entry point."""
    logger.info("═" * 80)
    logger.info("DATASET ENHANCEMENT PIPELINE - PRODUCTION GRADE")
    logger.info("═" * 80)
    
    # Load existing dataset.json
    dataset_path = Path("dataset.json")
    
    if not dataset_path.exists():
        logger.error(f"dataset.json not found at {dataset_path}")
        logger.info("Creating 10 sample entries instead...")
        entries = []
    else:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            entries = json.load(f)
        logger.info(f"Loaded {len(entries)} entries from dataset.json")
    
    # Initialize enhancer
    try:
        enhancer = DatasetEnhancer()
        logger.info("Dataset enhancer initialized")
    except ValueError as e:
        logger.error(f"Failed to initialize: {e}")
        sys.exit(1)
    
    # Enhance first 10 entries as sample
    sample_entries = entries[:10] if entries else []
    
    if not sample_entries:
        logger.info("No entries to enhance, creating sample questions...")
        sample_entries = [
            {
                "question": "Tell me about a complex system you designed and the challenges you faced.",
                "answers": {
                    "ideal": {
                        "text": "I designed a microservices-based e-commerce platform with 10+ services using Docker and Kubernetes. Key challenges were managing inter-service communication and ensuring consistency. I implemented RabbitMQ for async messaging and Redis for caching, achieving 99.9% uptime.",
                        "scores": {"technical_accuracy": 9, "clarity": 9, "communication": 8, "confidence": 9}
                    },
                    "average": {
                        "text": "I worked on a backend system for an online store. We had different parts for orders, payments, and products. It was challenging to make sure they all worked together smoothly. We used some standard tools and it mostly worked out.",
                        "scores": {"technical_accuracy": 6, "clarity": 6, "communication": 6, "confidence": 6}
                    },
                    "poor": {
                        "text": "Uh, I did some backend stuff, I guess. It was complicated. We had different parts and it was hard to connect them. I don't really remember the details.",
                        "scores": {"technical_accuracy": 2, "clarity": 2, "communication": 2, "confidence": 2}
                    }
                }
            },
            {
                "question": "How do you approach testing and quality assurance in your development process?",
                "answers": {
                    "ideal": {
                        "text": "I follow a comprehensive testing strategy: unit tests with >80% coverage using pytest, integration tests for service interactions, and end-to-end tests. I use CI/CD pipelines for automation and implement code reviews. For performance, I use load testing tools to ensure scalability.",
                        "scores": {"technical_accuracy": 9, "clarity": 8, "communication": 9, "confidence": 9}
                    },
                    "average": {
                        "text": "I write tests for my code, mostly unit tests. I've used some testing frameworks before. We also do code reviews to catch bugs. I think integration testing is important too, but I haven't done a lot of that.",
                        "scores": {"technical_accuracy": 6, "clarity": 5, "communication": 6, "confidence": 5}
                    },
                    "poor": {
                        "text": "I test things, like I run them and see if they work. Sometimes I write tests but not always. Testing is important I guess.",
                        "scores": {"technical_accuracy": 2, "clarity": 1, "communication": 2, "confidence": 1}
                    }
                }
            },
            {
                "question": "Describe your experience with databases and optimization techniques.",
                "answers": {
                    "ideal": {
                        "text": "I have 5+ years experience with both SQL and NoSQL databases. For SQL, I optimize through indexing strategies, query optimization, and normalization. For MongoDB, I use sharding and proper document design. I've implemented Redis caching for frequently accessed data, reducing query time by 60%.",
                        "scores": {"technical_accuracy": 9, "clarity": 8, "communication": 9, "confidence": 9}
                    },
                    "average": {
                        "text": "I've used MySQL and MongoDB in projects. I know you need to create indexes to make queries faster. I've also used some caching but I'm not sure about the best practices.",
                        "scores": {"technical_accuracy": 5, "clarity": 5, "communication": 5, "confidence": 5}
                    },
                    "poor": {
                        "text": "Yeah, I use databases for storing data. I think indexes are important? I don't really know much about optimization.",
                        "scores": {"technical_accuracy": 1, "clarity": 1, "communication": 1, "confidence": 1}
                    }
                }
            },
            {
                "question": "Tell me about a time you had to debug a critical production issue quickly.",
                "answers": {
                    "ideal": {
                        "text": "A payment service was timing out during peak hours. I immediately checked logs using ELK stack, identified database connection exhaustion. I implemented connection pooling as a hotfix, then root-caused it to inefficient queries. Refactored the queries with proper indexing, reducing API latency from 5s to 100ms.",
                        "scores": {"technical_accuracy": 9, "clarity": 9, "communication": 9, "confidence": 9}
                    },
                    "average": {
                        "text": "Once there was a problem with the API response time. I looked at the logs and tried to figure out what was wrong. I made a quick fix that helped, but I'm not sure if it was the best solution.",
                        "scores": {"technical_accuracy": 5, "clarity": 5, "communication": 5, "confidence": 5}
                    },
                    "poor": {
                        "text": "There was an issue and I had to fix it fast. I'm not really sure what I did exactly. It works now though.",
                        "scores": {"technical_accuracy": 2, "clarity": 1, "communication": 2, "confidence": 1}
                    }
                }
            },
            {
                "question": "How do you stay updated with the latest technologies and best practices?",
                "answers": {
                    "ideal": {
                        "text": "I invest time in continuous learning through technical blogs, GitHub trending projects, and conference talks. I contribute to open-source projects, which helps me stay current. I dedicate 5+ hours/week to learning and have certifications in cloud technologies. I mentor junior developers to reinforce my knowledge.",
                        "scores": {"technical_accuracy": 8, "clarity": 8, "communication": 9, "confidence": 9}
                    },
                    "average": {
                        "text": "I try to learn new things. I read some blogs and watch videos about technology sometimes. I think it's important to stay updated but I don't always have time.",
                        "scores": {"technical_accuracy": 4, "clarity": 4, "communication": 4, "confidence": 4}
                    },
                    "poor": {
                        "text": "I don't really focus on that much. New stuff comes out all the time and it's hard to keep up.",
                        "scores": {"technical_accuracy": 1, "clarity": 1, "communication": 1, "confidence": 1}
                    }
                }
            },
            {
                "question": "Describe a situation where you had to work with a difficult team member.",
                "answers": {
                    "ideal": {
                        "text": "A senior developer was resistant to code reviews. Instead of conflict, I requested a 1-on-1 to understand their concerns. Turns out they felt micromanaged. We established guidelines together, made reviews more collaborative. Within weeks, code quality improved and they became our strongest code reviewer.",
                        "scores": {"technical_accuracy": 8, "clarity": 9, "communication": 9, "confidence": 9}
                    },
                    "average": {
                        "text": "I had issues with someone once. We didn't agree on something at work. We talked about it and it got better. I think communication helps.",
                        "scores": {"technical_accuracy": 4, "clarity": 4, "communication": 4, "confidence": 4}
                    },
                    "poor": {
                        "text": "Yeah, sometimes people are difficult. I don't know, we just worked it out I guess.",
                        "scores": {"technical_accuracy": 1, "clarity": 1, "communication": 1, "confidence": 1}
                    }
                }
            },
            {
                "question": "What is your approach to writing scalable and maintainable code?",
                "answers": {
                    "ideal": {
                        "text": "I follow SOLID principles rigorously: single responsibility, open-closed through interfaces, and dependency injection. I write clean, self-documenting code with comprehensive tests. I use design patterns (Factory, Strategy) appropriately and maintain code review standards. Documentation and modularity enable future scalability.",
                        "scores": {"technical_accuracy": 9, "clarity": 8, "communication": 9, "confidence": 9}
                    },
                    "average": {
                        "text": "I try to write clean code. I know about design patterns and use them sometimes. Tests are important for maintainability. I try to follow best practices but sometimes deadlines don't allow.",
                        "scores": {"technical_accuracy": 6, "clarity": 6, "communication": 6, "confidence": 6}
                    },
                    "poor": {
                        "text": "I write code that works. I guess clean code is good? I'm not really sure about all those principles.",
                        "scores": {"technical_accuracy": 2, "clarity": 2, "communication": 2, "confidence": 2}
                    }
                }
            },
            {
                "question": "Tell me about your experience with cloud technologies and DevOps practices.",
                "answers": {
                    "ideal": {
                        "text": "5+ years with AWS (EC2, S3, Lambda, RDS). I've designed auto-scaling architectures, implemented CI/CD with Jenkins, containerized applications with Docker, and orchestrated with Kubernetes. I implemented Infrastructure-as-Code using Terraform, reducing deployment time by 80% and improving reliability.",
                        "scores": {"technical_accuracy": 9, "clarity": 9, "communication": 9, "confidence": 9}
                    },
                    "average": {
                        "text": "I've used AWS basics like EC2 and S3. I know about Docker and have deployed containers. I haven't worked much with Kubernetes or advanced DevOps stuff.",
                        "scores": {"technical_accuracy": 5, "clarity": 5, "communication": 5, "confidence": 5}
                    },
                    "poor": {
                        "text": "Cloud is like computing on the internet right? I've heard of Docker. Don't know much about DevOps.",
                        "scores": {"technical_accuracy": 1, "clarity": 1, "communication": 1, "confidence": 1}
                    }
                }
            },
            {
                "question": "How do you handle tight deadlines and prioritize your work?",
                "answers": {
                    "ideal": {
                        "text": "I assess urgency vs. importance using the Eisenhower Matrix. I break large tasks into smaller, manageable units with clear milestones. I communicate early about realistic timelines and proactively identify risks. For tight deadlines, I focus on MVP, cutting non-critical features while maintaining code quality.",
                        "scores": {"technical_accuracy": 8, "clarity": 9, "communication": 9, "confidence": 9}
                    },
                    "average": {
                        "text": "I try to work efficiently. I make lists and prioritize tasks. Sometimes tight deadlines are stressful but I usually get things done.",
                        "scores": {"technical_accuracy": 4, "clarity": 4, "communication": 4, "confidence": 4}
                    },
                    "poor": {
                        "text": "I just do the work. Deadlines are tight sometimes. I try my best.",
                        "scores": {"technical_accuracy": 1, "clarity": 1, "communication": 1, "confidence": 1}
                    }
                }
            },
            {
                "question": "What interests you most about this role and company?",
                "answers": {
                    "ideal": {
                        "text": "I'm drawn to this company's technical innovation in microservices and your open-source contributions. I've followed your architecture decisions and admire the scaling challenges you solve. This Backend Engineer role excites me because it tackles complex distributed systems problems, aligns with my growth goals, and I can contribute meaningfully.",
                        "scores": {"technical_accuracy": 8, "clarity": 8, "communication": 9, "confidence": 9}
                    },
                    "average": {
                        "text": "I'm interested in the backend work. Your company seems like a good place to work. I think I'd be a good fit for this role.",
                        "scores": {"technical_accuracy": 4, "clarity": 4, "communication": 4, "confidence": 4}
                    },
                    "poor": {
                        "text": "I need a job. Your company seems okay. This role sounds fine.",
                        "scores": {"technical_accuracy": 1, "clarity": 1, "communication": 1, "confidence": 1}
                    }
                }
            }
        ]
    
    # Enhance sample entries for Backend Engineer role
    logger.info(f"\nEnhancing {len(sample_entries)} entries for Backend Engineer role...")
    logger.info("This may take 5-10 minutes...")
    
    enhanced = await enhancer.enhance_dataset(
        sample_entries,
        target_role="Backend Engineer",
        experience_level="Mid",
        interview_type="Mixed"
    )
    
    # Save results
    output_path = Path("enhanced_dataset.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(
            [entry.to_dict() for entry in enhanced],
            f,
            indent=2,
            ensure_ascii=False
        )
    
    logger.info(f"\n✅ Enhanced dataset saved to: {output_path}")
    
    # Report statistics
    logger.info("\n" + "=" * 80)
    logger.info("ENHANCEMENT STATISTICS")
    logger.info("=" * 80)
    logger.info(f"Total processed:       {enhancer.stats['total_processed']}")
    logger.info(f"Cleaned:               {enhancer.stats['cleaned']}")
    logger.info(f"Enriched:              {enhancer.stats['enriched']}")
    logger.info(f"Skipped:               {enhancer.stats['skipped']}")
    logger.info(f"Success rate:          {(enhancer.stats['enriched'] / len(sample_entries) * 100):.1f}%")
    logger.info("=" * 80)
    
    logger.info(f"\n📊 Review the enhanced_dataset.json file (10 entries)")
    logger.info("Once approved, we'll:")
    logger.info("1. Generate for all 8 roles")
    logger.info("2. Insert into Supabase")
    logger.info("3. Create role-specific question batches")


if __name__ == "__main__":
    asyncio.run(main())
