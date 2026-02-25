"""
========================================
FEATURE EXTRACTOR FOR ANSWER SCORING
========================================

Purpose:
    Extract numerical features from question-answer pairs
    for use in Random Forest scoring model.

Features Extracted:
    1. word_count         - Total words in answer
    2. sentence_count     - Number of sentences
    3. avg_sentence_length - Words per sentence
    4. unique_word_ratio  - Vocabulary diversity
    5. keyword_match_ratio - Overlap with question keywords
    6. depth_indicator_score - Technical depth signals
    7. answer_length_normalized - Min-max normalized length

Design Philosophy:
    - These features capture WHAT a good answer looks like
    - They don't require LLM inference (fast & cheap)
    - They complement LLM evaluation with objective metrics

Author: InterviewAI Team
Date: 2026-02-17
========================================
"""

import re
import logging
from typing import List, Set, Dict, Any, Tuple
from collections import Counter

# Configure logging
logger = logging.getLogger(__name__)


# ========================================
# CONSTANTS
# ========================================

# Depth indicator words - signal technical depth and expertise
# These words commonly appear in strong technical answers
DEPTH_INDICATORS = [
    # Problem-solving words
    "because", "therefore", "however", "although", "consequently",
    
    # Technical architecture words
    "architecture", "design", "pattern", "framework", "system",
    "infrastructure", "microservice", "monolith", "distributed",
    
    # Performance/Quality words
    "optimized", "performance", "scalable", "efficient", "latency",
    "throughput", "cache", "memory", "complexity",
    
    # Implementation words
    "implemented", "designed", "developed", "built", "created",
    "deployed", "configured", "integrated", "refactored",
    
    # Professional language
    "handled", "managed", "led", "collaborated", "analyzed",
    "troubleshoot", "debug", "resolve", "improve",
    
    # Technical specifics
    "algorithm", "database", "api", "endpoint", "server",
    "client", "backend", "frontend", "testing", "ci/cd",
    
    # Best practices
    "best practice", "standard", "principle", "methodology",
    "agile", "scrum", "tdd", "solid", "dry"
]

# Common stopwords to exclude from keyword matching
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", 
    "to", "for", "of", "with", "by", "as", "is", "was", "are",
    "were", "be", "been", "being", "have", "has", "had", "do",
    "does", "did", "will", "would", "could", "should", "may",
    "might", "can", "this", "that", "these", "those", "i", "you",
    "he", "she", "it", "we", "they", "what", "which", "who",
    "how", "when", "where", "why", "your", "my", "me", "us"
}

# Normalization constants for answer length
# Based on typical interview answer lengths
MIN_ANSWER_LENGTH = 10   # Minimum expected words
MAX_ANSWER_LENGTH = 500  # Maximum expected words


# ========================================
# TEXT PREPROCESSING
# ========================================

def clean_text(text: str) -> str:
    """
    Clean and normalize text for feature extraction.
    
    Steps:
        1. Convert to lowercase
        2. Remove special characters
        3. Collapse multiple spaces
        
    Args:
        text: Raw text string
        
    Returns:
        Cleaned text
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Lowercase
    text = text.lower()
    
    # Keep alphanumeric and basic punctuation for sentence detection
    text = re.sub(r"[^a-z0-9\s\.\?\!]", " ", text)
    
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    
    return text.strip()


def tokenize(text: str) -> List[str]:
    """
    Split text into word tokens.
    
    Args:
        text: Cleaned text
        
    Returns:
        List of word tokens
    """
    if not text:
        return []
    
    # Split on whitespace
    words = text.split()
    
    # Remove punctuation from words
    words = [re.sub(r"[^\w]", "", w) for w in words]
    
    # Filter empty strings
    words = [w for w in words if w]
    
    return words


def split_sentences(text: str) -> List[str]:
    """
    Split text into sentences.
    
    Uses simple regex-based sentence splitting.
    
    Args:
        text: Input text
        
    Returns:
        List of sentences
    """
    if not text:
        return []
    
    # Split on sentence-ending punctuation
    sentences = re.split(r"[.!?]+", text)
    
    # Clean and filter empty
    sentences = [s.strip() for s in sentences if s.strip()]
    
    return sentences


def extract_keywords(text: str) -> Set[str]:
    """
    Extract meaningful keywords from text.
    
    Removes stopwords to get content-bearing words.
    
    Args:
        text: Input text
        
    Returns:
        Set of keywords
    """
    words = tokenize(clean_text(text))
    
    # Remove stopwords
    keywords = {w for w in words if w not in STOPWORDS and len(w) > 2}
    
    return keywords


# ========================================
# INDIVIDUAL FEATURE FUNCTIONS
# ========================================

def feature_word_count(answer: str) -> float:
    """
    Feature 1: Count total words in answer.
    
    Why this matters:
        - Longer answers typically show more thought
        - Very short answers often lack depth
        - But too long can be rambling
        
    Args:
        answer: Answer text
        
    Returns:
        Word count as float
    """
    words = tokenize(clean_text(answer))
    return float(len(words))


def feature_sentence_count(answer: str) -> float:
    """
    Feature 2: Count sentences in answer.
    
    Why this matters:
        - Multiple sentences suggest structured thinking
        - Single sentence answers are often too brief
        
    Args:
        answer: Answer text
        
    Returns:
        Sentence count as float
    """
    sentences = split_sentences(answer)
    return float(len(sentences))


def feature_avg_sentence_length(answer: str) -> float:
    """
    Feature 3: Calculate average words per sentence.
    
    Why this matters:
        - Very short sentences = choppy/incomplete thoughts
        - Very long sentences = unclear communication
        - Good range: 10-25 words per sentence
        
    Args:
        answer: Answer text
        
    Returns:
        Average sentence length
    """
    sentences = split_sentences(answer)
    
    if not sentences:
        return 0.0
    
    total_words = sum(len(tokenize(s)) for s in sentences)
    
    return total_words / len(sentences)


def feature_unique_word_ratio(answer: str) -> float:
    """
    Feature 4: Calculate vocabulary diversity.
    
    Formula: unique_words / total_words
    
    Why this matters:
        - Higher ratio = richer vocabulary
        - Lower ratio = repetitive language
        - Good answers use varied terminology
        
    Args:
        answer: Answer text
        
    Returns:
        Ratio between 0 and 1
    """
    words = tokenize(clean_text(answer))
    
    if not words:
        return 0.0
    
    unique_words = set(words)
    
    return len(unique_words) / len(words)


def feature_keyword_match_ratio(question: str, answer: str) -> float:
    """
    Feature 5: Measure overlap between question keywords and answer.
    
    Formula: matched_keywords / question_keywords
    
    Why this matters:
        - Good answers address the question directly
        - Keyword presence shows relevance
        - Off-topic answers have low match
        
    Args:
        question: Question text
        answer: Answer text
        
    Returns:
        Match ratio between 0 and 1
    """
    question_keywords = extract_keywords(question)
    answer_keywords = extract_keywords(answer)
    
    if not question_keywords:
        return 0.0
    
    # Find keywords present in both
    matched = question_keywords.intersection(answer_keywords)
    
    return len(matched) / len(question_keywords)


def feature_depth_indicator_score(answer: str) -> float:
    """
    Feature 6: Count depth indicator words.
    
    Why this matters:
        - Technical depth words signal expertise
        - Professional vocabulary suggests experience
        - More indicators = deeper answer
        
    Args:
        answer: Answer text
        
    Returns:
        Count of depth indicators found
    """
    answer_lower = answer.lower()
    
    count = 0
    for indicator in DEPTH_INDICATORS:
        # Use word boundary matching to avoid partial matches
        # e.g., "design" should not match in "designated"
        pattern = r"\b" + re.escape(indicator) + r"\b"
        matches = re.findall(pattern, answer_lower)
        count += len(matches)
    
    return float(count)


def feature_answer_length_normalized(answer: str) -> float:
    """
    Feature 7: Min-max normalized answer length.
    
    Formula: (length - min) / (max - min)
    
    Why this matters:
        - Normalizes length to 0-1 scale
        - Helps model compare answers fairly
        - Prevents length from dominating other features
        
    Args:
        answer: Answer text
        
    Returns:
        Normalized length between 0 and 1
    """
    word_count = feature_word_count(answer)
    
    # Apply min-max normalization
    # Clamp to [0, 1] range
    normalized = (word_count - MIN_ANSWER_LENGTH) / (MAX_ANSWER_LENGTH - MIN_ANSWER_LENGTH)
    
    # Clamp to valid range
    normalized = max(0.0, min(1.0, normalized))
    
    return normalized


# ========================================
# MAIN FEATURE EXTRACTION FUNCTION
# ========================================

def extract_features(question: str, answer: str) -> List[float]:
    """
    Extract all features from a question-answer pair.
    
    This is the main function called by the training script.
    
    Feature Order (IMPORTANT - must match training):
        0: word_count
        1: sentence_count
        2: avg_sentence_length
        3: unique_word_ratio
        4: keyword_match_ratio
        5: depth_indicator_score
        6: answer_length_normalized
        
    Args:
        question: Interview question text
        answer: Candidate's answer text
        
    Returns:
        List of 7 numeric features
    """
    features = [
        feature_word_count(answer),
        feature_sentence_count(answer),
        feature_avg_sentence_length(answer),
        feature_unique_word_ratio(answer),
        feature_keyword_match_ratio(question, answer),
        feature_depth_indicator_score(answer),
        feature_answer_length_normalized(answer),
    ]
    
    return features


def get_feature_names() -> List[str]:
    """
    Get human-readable names for each feature.
    
    Used for:
        - Feature importance visualization
        - Debugging
        - Documentation
        
    Returns:
        List of feature names in order
    """
    return [
        "word_count",
        "sentence_count",
        "avg_sentence_length",
        "unique_word_ratio",
        "keyword_match_ratio",
        "depth_indicator_score",
        "answer_length_normalized"
    ]


# ========================================
# UTILITY FUNCTIONS
# ========================================

def explain_features(question: str, answer: str) -> Dict[str, Any]:
    """
    Get detailed feature breakdown for debugging.
    
    Useful for understanding model predictions.
    
    Args:
        question: Question text
        answer: Answer text
        
    Returns:
        Dictionary with feature names and values
    """
    features = extract_features(question, answer)
    names = get_feature_names()
    
    return {
        name: value 
        for name, value in zip(names, features)
    }


# ========================================
# TESTING
# ========================================

def _test_feature_extraction():
    """
    Quick test to verify feature extraction works.
    """
    question = "Tell me about your experience with Python and REST APIs."
    
    # Weak answer (should score low)
    weak_answer = "I know Python."
    
    # Strong answer (should score high)
    strong_answer = """
    I have extensive experience with Python, having implemented several backend 
    services using Flask and FastAPI. In my previous role, I designed and built 
    a RESTful API architecture that handled over 10,000 requests per minute. 
    I optimized the system for performance by implementing caching strategies 
    and database query optimization. I also set up CI/CD pipelines for automated 
    testing and deployment.
    """
    
    print("=" * 60)
    print("🧪 FEATURE EXTRACTION TEST")
    print("=" * 60)
    
    print(f"\n📝 Question: {question}")
    
    print("\n--- Weak Answer Features ---")
    weak_features = explain_features(question, weak_answer)
    for name, value in weak_features.items():
        print(f"   {name}: {value:.3f}")
    
    print("\n--- Strong Answer Features ---")
    strong_features = explain_features(question, strong_answer)
    for name, value in strong_features.items():
        print(f"   {name}: {value:.3f}")
    
    print("\n✅ Feature extraction working correctly!")


if __name__ == "__main__":
    _test_feature_extraction()
