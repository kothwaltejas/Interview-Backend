"""
Dataset Generator Service for InterviewAI

Generates training and evaluation datasets by:
1. Creating multiple answer variations (ideal, average, poor) for each question
2. Evaluating answers on multiple criteria
3. Storing structured data for ML model training
4. Supporting batch processing with retry logic and parallel execution

Usage:
    from services.dataset_generator import DatasetGenerator
    
    generator = DatasetGenerator()
    dataset = await generator.generate_dataset(
        questions=questions_list,
        output_file="dataset.json"
    )
"""

import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
import aiohttp
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)


class DatasetEntry:
    """Represents a single dataset entry with question and answer variations."""
    
    def __init__(self, question: str, question_metadata: Optional[Dict[str, Any]] = None):
        self.question = question
        self.question_metadata = question_metadata or {}
        self.answers = {
            "ideal": None,
            "average": None,
            "poor": None
        }
        self.timestamp = datetime.utcnow().isoformat()
        self.generation_attempts = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entry to dictionary for JSON serialization."""
        return {
            "question": self.question,
            "question_metadata": self.question_metadata,
            "answers": {
                level: {
                    "text": data["text"],
                    "scores": data["scores"]
                } if data else None
                for level, data in self.answers.items()
            },
            "timestamp": self.timestamp,
            "generation_attempts": self.generation_attempts
        }


class DatasetGenerator:
    """Generates training datasets for interview answer evaluation models."""
    
    def __init__(self, groq_api_key: Optional[str] = None):
        """
        Initialize the dataset generator.
        
        Args:
            groq_api_key: GROQ API key. If None, uses GROQ_API_KEY env var.
        """
        import os
        self.api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in environment or arguments")
        
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "llama-3.3-70b-versatile"
        self.max_retries = 3
        self.batch_size = 10  # Parallel batch size
        
        logger.info("Dataset generator initialized")
    
    async def _call_groq(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        retry_count: int = 0
    ) -> Optional[str]:
        """
        Call GROQ API with retry logic.
        
        Args:
            prompt: The prompt to send to GROQ
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            retry_count: Current retry attempt number
            
        Returns:
            API response text or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                
                response = await client.post(
                    self.base_url,
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    logger.warning(f"GROQ API error: {response.status_code} - {response.text}")
                    
                    if retry_count < self.max_retries:
                        logger.info(f"Retrying... (attempt {retry_count + 1}/{self.max_retries})")
                        await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                        return await self._call_groq(prompt, max_tokens, temperature, retry_count + 1)
                    
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("GROQ API timeout")
            if retry_count < self.max_retries:
                await asyncio.sleep(2 ** retry_count)
                return await self._call_groq(prompt, max_tokens, temperature, retry_count + 1)
            return None
            
        except Exception as e:
            logger.error(f"GROQ API error: {str(e)}")
            if retry_count < self.max_retries:
                await asyncio.sleep(2 ** retry_count)
                return await self._call_groq(prompt, max_tokens, temperature, retry_count + 1)
            return None
    
    async def _generate_answer(
        self,
        question: str,
        answer_type: str,  # "ideal", "average", "poor"
        job_context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Generate an answer for a specific quality level.
        
        Args:
            question: The interview question
            answer_type: Type of answer to generate (ideal, average, poor)
            job_context: Optional job context (role, level, etc.)
            
        Returns:
            Generated answer text or None if failed
        """
        
        context_info = ""
        if job_context:
            role = job_context.get("target_role", "Software Developer")
            level = job_context.get("experience_level", "3-5 years")
            context_info = f"\nTarget Role: {role}\nExperience Level: {level}\n"
        
        quality_descriptions = {
            "ideal": "an EXCELLENT candidate with strong technical knowledge, clear communication, and confidence",
            "average": "an AVERAGE candidate with basic understanding, some communication gaps, and moderate confidence",
            "poor": "a WEAK candidate with limited knowledge, poor communication, and low confidence"
        }
        
        quality_desc = quality_descriptions.get(answer_type, "a candidate")
        
        prompt = f"""Generate a {quality_desc} answering this interview question.

Question: "{question}"{context_info}

Requirements:
- Answer should be realistic for the experience level
- Keep answer between 100-200 words
- For IDEAL: Include specific examples, technical depth, confidence
- For AVERAGE: Basic answer with some details, minor gaps
- For POOR: Vague answer, lacks focus, shows uncertainty

Return ONLY the answer text, no labels or explanations:"""
        
        return await self._call_groq(prompt, max_tokens=500, temperature=0.8)
    
    async def _evaluate_answer(
        self,
        question: str,
        answer: str,
        job_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, int]]:
        """
        Evaluate an answer on multiple criteria.
        
        Args:
            question: The interview question
            answer: The candidate's answer
            job_context: Optional job context
            
        Returns:
            Dictionary with scores (1-10 for each criterion) or None if failed
        """
        
        context_info = ""
        if job_context:
            role = job_context.get("target_role", "Software Developer")
            level = job_context.get("experience_level", "3-5 years")
            context_info = f"\nTarget Role: {role}\nExperience Level: {level}\n"
        
        prompt = f"""Evaluate this interview answer on FOUR criteria, each on a scale of 1-10.

Question: "{question}"

Answer: "{answer}"{context_info}

Scoring Criteria:
1. technical_accuracy: How technically correct and accurate is the answer?
2. clarity: How clear and well-structured is the response?
3. communication: How well is the information communicated?
4. confidence: How confident and assertive is the tone?

Return ONLY valid JSON (no markdown, no extra text):
{{
  "technical_accuracy": <1-10>,
  "clarity": <1-10>,
  "communication": <1-10>,
  "confidence": <1-10>
}}"""
        
        response = await self._call_groq(prompt, max_tokens=200, temperature=0.3)
        
        if not response:
            return None
        
        try:
            # Extract JSON from response (handles some markdown formatting)
            response_clean = response.strip()
            if "```json" in response_clean:
                response_clean = response_clean.split("```json")[1].split("```")[0]
            elif "```" in response_clean:
                response_clean = response_clean.split("```")[1].split("```")[0]
            
            scores = json.loads(response_clean)
            
            # Validate scores are in range
            for criterion in ["technical_accuracy", "clarity", "communication", "confidence"]:
                if criterion not in scores:
                    logger.warning(f"Missing criterion: {criterion}")
                    return None
                
                score = scores[criterion]
                if not isinstance(score, (int, float)) or score < 1 or score > 10:
                    logger.warning(f"Invalid score for {criterion}: {score}")
                    return None
            
            return {
                "technical_accuracy": int(scores["technical_accuracy"]),
                "clarity": int(scores["clarity"]),
                "communication": int(scores["communication"]),
                "confidence": int(scores["confidence"])
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse evaluation JSON: {e}")
            logger.error(f"Response was: {response}")
            return None
    
    async def generate_answer_variations(
        self,
        question: str,
        job_context: Optional[Dict[str, Any]] = None
    ) -> Optional[DatasetEntry]:
        """
        Generate three answer variations (ideal, average, poor) and evaluate each.
        
        Args:
            question: The interview question
            job_context: Optional job context
            
        Returns:
            DatasetEntry with all answers and scores, or None if failed
        """
        
        entry = DatasetEntry(question, job_context)
        entry.generation_attempts = 1
        
        try:
            logger.info(f"Generating answers for: {question[:60]}...")
            
            # Generate all three answer types with retry
            tasks = [
                self._generate_answer(question, "ideal", job_context),
                self._generate_answer(question, "average", job_context),
                self._generate_answer(question, "poor", job_context)
            ]
            
            answers = await asyncio.gather(*tasks)
            ideal_answer, avg_answer, poor_answer = answers
            
            if not all([ideal_answer, avg_answer, poor_answer]):
                logger.error(f"Failed to generate all answer types for: {question[:60]}")
                return None
            
            # Evaluate each answer
            eval_tasks = [
                self._evaluate_answer(question, ideal_answer, job_context),
                self._evaluate_answer(question, avg_answer, job_context),
                self._evaluate_answer(question, poor_answer, job_context)
            ]
            
            evaluations = await asyncio.gather(*eval_tasks)
            ideal_scores, avg_scores, poor_scores = evaluations
            
            if not all([ideal_scores, avg_scores, poor_scores]):
                logger.error(f"Failed to evaluate all answers for: {question[:60]}")
                return None
            
            # Store results
            entry.answers["ideal"] = {"text": ideal_answer, "scores": ideal_scores}
            entry.answers["average"] = {"text": avg_answer, "scores": avg_scores}
            entry.answers["poor"] = {"text": poor_answer, "scores": poor_scores}
            
            logger.info(f"✅ Successfully generated dataset entry for: {question[:60]}")
            return entry
            
        except Exception as e:
            logger.error(f"Error generating answers: {str(e)}")
            return None
    
    async def generate_dataset(
        self,
        questions: List[str],
        job_contexts: Optional[List[Dict[str, Any]]] = None,
        output_file: str = "dataset.json",
        save_to_supabase: bool = False
    ) -> Dict[str, Any]:
        """
        Generate complete dataset for all questions.
        
        Args:
            questions: List of interview questions
            job_contexts: Optional list of job contexts (one per question or use default)
            output_file: Path to save JSON output
            save_to_supabase: Whether to save to Supabase table
            
        Returns:
            Dictionary with dataset stats and results
        """
        
        logger.info(f"Starting dataset generation for {len(questions)} questions")
        
        # Use default job context if not provided
        if not job_contexts:
            job_contexts = [
                {
                    "target_role": "Senior Backend Engineer",
                    "experience_level": "3-5 years",
                    "interview_type": "Technical"
                }
            ] * len(questions)
        
        dataset = []
        successful = 0
        failed = 0
        
        # Process in batches
        for i in range(0, len(questions), self.batch_size):
            batch = questions[i:i + self.batch_size]
            batch_contexts = job_contexts[i:i + self.batch_size]
            
            logger.info(f"Processing batch {i // self.batch_size + 1}/{(len(questions) + self.batch_size - 1) // self.batch_size}")
            
            # Generate entries in parallel
            tasks = [
                self.generate_answer_variations(q, ctx)
                for q, ctx in zip(batch, batch_contexts)
            ]
            
            entries = await asyncio.gather(*tasks)
            
            for entry in entries:
                if entry is not None:
                    dataset.append(entry.to_dict())
                    successful += 1
                else:
                    failed += 1
            
            # Small delay between batches
            if i + self.batch_size < len(questions):
                await asyncio.sleep(1)
        
        # Save to JSON file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(dataset, f, indent=2)
        
        logger.info(f"Dataset saved to: {output_path}")
        
        # Optionally save to Supabase
        if save_to_supabase:
            await self._save_to_supabase(dataset)
        
        stats = {
            "total_questions": len(questions),
            "successful_entries": successful,
            "failed_entries": failed,
            "output_file": str(output_path),
            "timestamp": datetime.utcnow().isoformat(),
            "data_size_mb": output_path.stat().st_size / (1024 * 1024)
        }
        
        logger.info(f"Dataset generation complete: {stats}")
        return stats
    
    async def _save_to_supabase(self, dataset: List[Dict[str, Any]]) -> bool:
        """
        Save generated dataset to Supabase table.
        
        Args:
            dataset: List of dataset entries
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from database.supabase_client import supabase
            
            if not supabase:
                logger.warning("Supabase not configured, skipping database save")
                return False
            
            logger.info(f"Saving {len(dataset)} entries to Supabase...")
            
            # Convert to format for Supabase
            records = [
                {
                    "question": entry["question"],
                    "question_metadata": json.dumps(entry.get("question_metadata", {})),
                    "ideal_answer": entry["answers"]["ideal"]["text"] if entry["answers"]["ideal"] else None,
                    "ideal_scores": json.dumps(entry["answers"]["ideal"]["scores"]) if entry["answers"]["ideal"] else None,
                    "average_answer": entry["answers"]["average"]["text"] if entry["answers"]["average"] else None,
                    "average_scores": json.dumps(entry["answers"]["average"]["scores"]) if entry["answers"]["average"] else None,
                    "poor_answer": entry["answers"]["poor"]["text"] if entry["answers"]["poor"] else None,
                    "poor_scores": json.dumps(entry["answers"]["poor"]["scores"]) if entry["answers"]["poor"] else None,
                    "created_at": entry.get("timestamp")
                }
                for entry in dataset
            ]
            
            # Save in batches
            for i in range(0, len(records), 100):
                batch = records[i:i + 100]
                supabase.table("generated_datasets").insert(batch).execute()
                logger.info(f"Saved batch {i // 100 + 1}/{(len(records) + 99) // 100}")
            
            logger.info(f"✅ Successfully saved {len(dataset)} entries to Supabase")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save to Supabase: {str(e)}")
            return False


async def generate_sample_dataset(num_questions: int = 10) -> None:
    """
    Generate a sample dataset for testing.
    
    Args:
        num_questions: Number of questions to generate for
    """
    
    # Sample questions
    sample_questions = [
        "Tell me about a complex system you designed and the challenges you faced",
        "How do you approach debugging a production issue under time pressure?",
        "Describe your experience with microservices architecture",
        "How do you ensure code quality in a team setting?",
        "Tell me about a time you had to learn a new technology quickly",
        "How do you handle technical debt in your projects?",
        "Describe your approach to API design",
        "How do you optimize database queries for performance?",
        "Tell me about your experience with CI/CD pipelines",
        "How do you approach system scalability and load balancing?"
    ][:num_questions]
    
    # Sample job contexts
    job_contexts = [
        {
            "target_role": "Senior Backend Engineer",
            "experience_level": "3-5 years",
            "interview_type": "Technical"
        }
    ] * len(sample_questions)
    
    generator = DatasetGenerator()
    
    stats = await generator.generate_dataset(
        questions=sample_questions,
        job_contexts=job_contexts,
        output_file="dataset_sample.json",
        save_to_supabase=False  # Set to True if Supabase configured
    )
    
    print(f"\n{'='*60}")
    print("DATASET GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"Questions processed: {stats['total_questions']}")
    print(f"Successful entries: {stats['successful_entries']}")
    print(f"Failed entries: {stats['failed_entries']}")
    print(f"Output file: {stats['output_file']}")
    print(f"Data size: {stats['data_size_mb']:.2f} MB")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # Run sample generation
    asyncio.run(generate_sample_dataset(num_questions=3))
