"""
========================================
EXPORT TRAINING DATA FROM SUPABASE
========================================

Purpose:
    Extract historical interview answer data from Supabase database
    and prepare it for ML model training.

Data Source:
    Supabase PostgreSQL → interview_answers table

Output:
    training/dataset.csv

Author: InterviewAI Team
Date: 2026-02-17
========================================
"""

import os
import sys
import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional

# ========================================
# CONFIGURATION
# ========================================

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ========================================
# CONSTANTS
# ========================================

# Minimum word count for valid answers
MIN_WORD_COUNT = 10

# Output file path
OUTPUT_DIR = Path(__file__).parent
OUTPUT_FILE = OUTPUT_DIR / "dataset.csv"


# ========================================
# SUPABASE CONNECTION
# ========================================

def get_supabase_config() -> Dict[str, str]:
    """
    Load Supabase configuration from environment variables.
    
    Returns:
        Dictionary with url and key
        
    Raises:
        ValueError if required env vars are missing
    """
    # Load .env file from backend directory
    from dotenv import load_dotenv
    
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"✅ Loaded .env from: {env_path}")
    else:
        load_dotenv()
        logger.warning("⚠️ Using system environment variables")
    
    # Get required variables
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    
    if not url:
        raise ValueError("❌ SUPABASE_URL not found in environment")
    if not key:
        raise ValueError("❌ SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY not found")
    
    return {"url": url, "key": key}


def fetch_interview_answers() -> List[Dict[str, Any]]:
    """
    Fetch all interview answers from Supabase.
    
    Process:
        1. Connect to Supabase REST API
        2. Query interview_answers table
        3. Select required columns only
        
    Returns:
        List of answer records as dictionaries
    """
    import httpx
    
    config = get_supabase_config()
    
    # Build REST API URL
    # Format: {SUPABASE_URL}/rest/v1/{table}
    rest_url = f"{config['url']}/rest/v1/interview_answers"
    
    # Select only needed columns (optimization)
    params = {
        "select": "question_text,answer_text,category,difficulty,score"
    }
    
    # Headers for authentication
    headers = {
        "apikey": config["key"],
        "Authorization": f"Bearer {config['key']}",
        "Content-Type": "application/json"
    }
    
    logger.info(f"📡 Fetching data from: {rest_url}")
    
    try:
        # Make HTTP request
        with httpx.Client(timeout=30.0) as client:
            response = client.get(rest_url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"✅ Fetched {len(data)} records from interview_answers")
            return data
            
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ HTTP Error: {e.response.status_code} - {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"❌ Failed to fetch data: {e}")
        raise


# ========================================
# DATA CLEANING & FILTERING
# ========================================

def count_words(text: str) -> int:
    """Count words in text, handling None/empty values."""
    if not text or not isinstance(text, str):
        return 0
    return len(text.strip().split())


def clean_and_filter_data(raw_data: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Clean and filter the raw data for training.
    
    Filtering Criteria:
        1. score IS NOT NULL (we need labels!)
        2. answer_text has > 10 words (meaningful answers)
        3. question_text is not empty
        
    Cleaning Steps:
        1. Remove rows with missing critical fields
        2. Strip whitespace from text fields
        3. Normalize category/difficulty to lowercase
        4. Convert score to float
        
    Args:
        raw_data: List of records from Supabase
        
    Returns:
        Cleaned pandas DataFrame ready for feature extraction
    """
    logger.info("🧹 Starting data cleaning and filtering...")
    
    # Convert to DataFrame
    df = pd.DataFrame(raw_data)
    
    initial_count = len(df)
    logger.info(f"   Initial records: {initial_count}")
    
    # ========================================
    # STEP 1: Handle missing values
    # ========================================
    
    # Drop rows where score is NULL (we need labels!)
    df = df.dropna(subset=["score"])
    after_score_filter = len(df)
    logger.info(f"   After score filter: {after_score_filter} (removed {initial_count - after_score_filter} without scores)")
    
    # Drop rows where answer_text is NULL or empty
    df = df[df["answer_text"].notna()]
    df = df[df["answer_text"].str.strip() != ""]
    
    # Drop rows where question_text is NULL or empty
    df = df[df["question_text"].notna()]
    df = df[df["question_text"].str.strip() != ""]
    
    logger.info(f"   After text filter: {len(df)}")
    
    # ========================================
    # STEP 2: Word count filter
    # ========================================
    
    # Calculate word counts
    df["word_count"] = df["answer_text"].apply(count_words)
    
    # Filter by minimum word count
    df = df[df["word_count"] > MIN_WORD_COUNT]
    logger.info(f"   After word count filter (>{MIN_WORD_COUNT} words): {len(df)}")
    
    # ========================================
    # STEP 3: Clean text fields
    # ========================================
    
    # Strip whitespace
    df["question_text"] = df["question_text"].str.strip()
    df["answer_text"] = df["answer_text"].str.strip()
    
    # Normalize category and difficulty to lowercase
    df["category"] = df["category"].fillna("unknown").str.lower().str.strip()
    df["difficulty"] = df["difficulty"].fillna("medium").str.lower().str.strip()
    
    # ========================================
    # STEP 4: Clean score
    # ========================================
    
    # Ensure score is numeric
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    
    # Remove any invalid scores (should be 1-10)
    df = df[(df["score"] >= 1) & (df["score"] <= 10)]
    
    # ========================================
    # STEP 5: Remove temporary columns
    # ========================================
    
    # We calculated word_count for filtering, but feature_extractor will recalculate
    # so we can keep or drop it. Let's keep it for reference.
    
    final_count = len(df)
    logger.info(f"✅ Final dataset: {final_count} records ({final_count/initial_count*100:.1f}% retention)")
    
    return df


# ========================================
# EXPORT FUNCTION
# ========================================

def export_to_csv(df: pd.DataFrame, output_path: Path) -> None:
    """
    Export cleaned DataFrame to CSV file.
    
    Args:
        df: Cleaned DataFrame
        output_path: Path to save CSV
    """
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save to CSV
    df.to_csv(output_path, index=False, encoding="utf-8")
    
    logger.info(f"💾 Dataset saved to: {output_path}")
    logger.info(f"   Columns: {list(df.columns)}")
    logger.info(f"   Shape: {df.shape}")


def print_dataset_summary(df: pd.DataFrame) -> None:
    """
    Print summary statistics of the dataset.
    
    This helps understand data distribution before training.
    """
    print("\n" + "=" * 50)
    print("📊 DATASET SUMMARY")
    print("=" * 50)
    
    print(f"\n📝 Total Records: {len(df)}")
    
    print("\n📈 Score Distribution:")
    print(df["score"].describe())
    
    print("\n📂 Category Distribution:")
    print(df["category"].value_counts())
    
    print("\n🎯 Difficulty Distribution:")
    print(df["difficulty"].value_counts())
    
    print("\n📏 Word Count Statistics:")
    print(df["word_count"].describe())
    
    print("\n" + "=" * 50)


# ========================================
# MAIN EXECUTION
# ========================================

def main():
    """
    Main entry point for data export.
    
    Pipeline:
        1. Connect to Supabase
        2. Fetch interview_answers
        3. Clean and filter data
        4. Export to CSV
        5. Print summary
    """
    print("\n" + "=" * 60)
    print("🚀 INTERVIEW ANSWER DATA EXPORT")
    print("   Exporting training data from Supabase")
    print("=" * 60 + "\n")
    
    try:
        # Step 1: Fetch data
        logger.info("📥 Step 1: Fetching data from Supabase...")
        raw_data = fetch_interview_answers()
        
        if not raw_data:
            logger.warning("⚠️ No data found in interview_answers table!")
            logger.info("💡 Tip: Run some interviews first to generate training data.")
            return
        
        # Step 2: Clean and filter
        logger.info("\n🧹 Step 2: Cleaning and filtering data...")
        df = clean_and_filter_data(raw_data)
        
        if len(df) == 0:
            logger.warning("⚠️ No valid records after filtering!")
            logger.info("💡 Tip: Ensure answers have scores and >10 words.")
            return
        
        # Step 3: Export
        logger.info("\n💾 Step 3: Exporting to CSV...")
        export_to_csv(df, OUTPUT_FILE)
        
        # Step 4: Summary
        print_dataset_summary(df)
        
        print("\n✅ Export complete!")
        print(f"   Output: {OUTPUT_FILE}")
        print("   Next step: Run train_model.py")
        
    except Exception as e:
        logger.error(f"\n❌ Export failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
