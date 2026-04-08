#!/usr/bin/env python3
"""
Standalone Dataset Generation Script for InterviewAI

Generates training datasets by creating answer variations (ideal, average, poor)
for interview questions and evaluating them on multiple criteria.

Usage:
    python generate_dataset.py --questions 1000 --output dataset.json
    python generate_dataset.py --file questions.json --supabase
    python generate_dataset.py --test  # Generate small sample

Environment:
    GROQ_API_KEY: Required (from console.groq.com)
    SUPABASE_URL: Required if using --supabase flag
    SUPABASE_SERVICE_KEY: Required if using --supabase flag
"""

import argparse
import asyncio
import json
import logging
import sys
import os
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.dataset_generator import DatasetGenerator

# Configure logging with UTF-8 encoding for Windows compatibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dataset_generation.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Fix Windows encoding issue by setting UTF-8 for stdout
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
logger = logging.getLogger(__name__)


class DatasetGenerationScript:
    """Main script for dataset generation."""
    
    def __init__(self):
        self.generator = None
    
    async def initialize(self):
        """Initialize the dataset generator."""
        try:
            self.generator = DatasetGenerator()
            logger.info("✅ Dataset generator initialized")
        except ValueError as e:
            logger.error(f"❌ Failed to initialize: {e}")
            sys.exit(1)
    
    def load_questions_from_file(self, file_path: str) -> List[str]:
        """Load questions from JSON or text file."""
        path = Path(file_path)
        
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            sys.exit(1)
        
        try:
            if path.suffix == '.json':
                with open(path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return [q if isinstance(q, str) else q.get('question', str(q)) for q in data]
                    elif isinstance(data, dict) and 'questions' in data:
                        return data['questions']
            else:
                # Text file - one question per line
                with open(path, 'r') as f:
                    return [line.strip() for line in f if line.strip()]
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            sys.exit(1)
    
    def generate_sample_questions(self, count: int) -> List[str]:
        """Generate sample questions for testing."""
        base_questions = [
            "Tell me about a complex system you designed and the challenges you faced",
            "How do you approach debugging a production issue under time pressure?",
            "Describe your experience with microservices architecture",
            "How do you ensure code quality in a team setting?",
            "Tell me about a time you had to learn a new technology quickly",
            "How do you handle technical debt in your projects?",
            "Describe your approach to API design and versioning",
            "How do you optimize database queries for performance?",
            "Tell me about your experience with CI/CD pipelines and DevOps",
            "How do you approach system scalability and load balancing?",
            "Describe a situation where you had to refactor legacy code",
            "How do you implement security best practices in your applications?",
            "Tell me about your experience with cloud platforms like AWS or GCP",
            "How do you approach testing in your development workflow?",
            "Describe your experience with containerization and Kubernetes",
            "How do you handle version control and code review processes?",
            "Tell me about a time you mentored junior developers",
            "How do you stay updated with new technologies and trends?",
            "Describe your approach to monitoring and logging in production",
            "How do you balance technical excellence with business requirements?"
        ]
        
        # Cycle through base questions to reach desired count
        questions = []
        for i in range(count):
            base = base_questions[i % len(base_questions)]
            if i >= len(base_questions):
                # Add variation for duplicates
                questions.append(f"{base} (Variation {i // len(base_questions)})")
            else:
                questions.append(base)
        
        return questions[:count]
    
    async def run(
        self,
        num_questions: int = 100,
        questions_file: str = None,
        output_file: str = "dataset.json",
        save_to_supabase: bool = False,
        batch_size: int = 10
    ):
        """
        Run dataset generation.
        
        Args:
            num_questions: Number of questions to generate (if not using file)
            questions_file: Path to file with questions
            output_file: Path to save JSON output
            save_to_supabase: Whether to save to Supabase
            batch_size: Batch processing size
        """
        
        await self.initialize()
        
        # Load or generate questions
        if questions_file:
            logger.info(f"Loading questions from: {questions_file}")
            questions = self.load_questions_from_file(questions_file)
        else:
            logger.info(f"Generating {num_questions} sample questions")
            questions = self.generate_sample_questions(num_questions)
        
        logger.info(f"Total questions to process: {len(questions)}")
        
        # Generate job contexts (demo: use same for all)
        job_contexts = [
            {
                "target_role": "Senior Backend Engineer",
                "experience_level": "3-5 years",
                "interview_type": "Technical"
            }
        ] * len(questions)
        
        # Set batch size
        self.generator.batch_size = batch_size
        
        # Run generation
        logger.info(f"Beginning dataset generation (batch size: {batch_size})")
        logger.info("This may take a while depending on the number of questions...")
        print("\n" + "="*70)
        
        stats = await self.generator.generate_dataset(
            questions=questions,
            job_contexts=job_contexts,
            output_file=output_file,
            save_to_supabase=save_to_supabase
        )
        
        # Print results
        print("="*70)
        print("✅ DATASET GENERATION COMPLETE")
        print("="*70)
        print(f"Questions processed:     {stats['total_questions']:,}")
        print(f"Successful entries:      {stats['successful_entries']:,}")
        print(f"Failed entries:          {stats['failed_entries']:,}")
        print(f"Success rate:            {(stats['successful_entries'] / stats['total_questions'] * 100):.1f}%")
        print(f"Output file:             {stats['output_file']}")
        print(f"Data size:               {stats['data_size_mb']:.2f} MB")
        print(f"Generated at:            {stats['timestamp']}")
        
        if save_to_supabase:
            print(f"Supabase:                ✅ Saved")
        else:
            print(f"Supabase:                ⏭️  Use --supabase to enable")
        
        print("="*70 + "\n")
        
        # Print sample entry structure
        output_path = Path(stats['output_file'])
        if output_path.exists() and stats['successful_entries'] > 0:
            with open(output_path, 'r') as f:
                sample_data = json.load(f)
                if sample_data:
                    print("📋 SAMPLE DATASET ENTRY:")
                    print("-"*70)
                    print(json.dumps(sample_data[0], indent=2)[:1000] + "...")
                    print("-"*70 + "\n")


async def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(
        description="Generate training dataset for InterviewAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 100 sample questions
  python generate_dataset.py --questions 100
  
  # Generate from existing questions file
  python generate_dataset.py --file questions.json --output my_dataset.json
  
  # Generate 1000 questions and save to Supabase
  python generate_dataset.py --questions 1000 --supabase
  
  # Test with just 3 questions
  python generate_dataset.py --test
        """
    )
    
    parser.add_argument(
        '--questions',
        type=int,
        default=100,
        help='Number of questions to generate (default: 100)'
    )
    
    parser.add_argument(
        '--file',
        type=str,
        help='Load questions from file (JSON or TXT)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='dataset.json',
        help='Output file path (default: dataset.json)'
    )
    
    parser.add_argument(
        '--supabase',
        action='store_true',
        help='Save results to Supabase table'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Parallel batch size (default: 10, range: 5-20)'
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help='Run test with 3 questions (quick validation)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Adjust verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate batch size
    if args.batch_size < 5 or args.batch_size > 20:
        logger.error("Batch size must be between 5 and 20")
        sys.exit(1)
    
    # Run test mode if requested
    num_questions = 3 if args.test else args.questions
    questions_file = args.file
    
    script = DatasetGenerationScript()
    
    try:
        await script.run(
            num_questions=num_questions,
            questions_file=questions_file,
            output_file=args.output,
            save_to_supabase=args.supabase,
            batch_size=args.batch_size
        )
    except KeyboardInterrupt:
        logger.info("\n⚠️  Generation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
