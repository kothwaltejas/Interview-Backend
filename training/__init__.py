"""
========================================
INTERVIEW ANSWER SCORING - ML TRAINING MODULE
========================================

This module provides supervised machine learning for
interview answer evaluation.

Components:
    - export_training_data: Extract data from Supabase
    - feature_extractor: Text feature extraction
    - train_model: Random Forest training pipeline

Usage:
    # Step 1: Export training data
    python export_training_data.py
    
    # Step 2: Train model
    python train_model.py
    
    # Step 3: Use in production (after integration)
    from training.train_model import predict_score
    score = predict_score(question, answer)

Author: InterviewAI Team
Date: 2026-02-17
========================================
"""

from .feature_extractor import extract_features, get_feature_names
from .train_model import predict_score, load_model

__all__ = [
    "extract_features",
    "get_feature_names", 
    "predict_score",
    "load_model"
]
