"""
========================================
RANDOM FOREST ANSWER SCORING MODEL
========================================

Purpose:
    Train a supervised ML model to predict interview answer scores (1-10)
    based on extracted text features.

Model Type:
    Random Forest Regressor (scikit-learn)

Why Random Forest?
    1. Handles non-linear relationships between features and scores
    2. Robust to overfitting with proper hyperparameters
    3. Provides feature importance rankings
    4. No need for feature scaling (tree-based)
    5. Works well with small to medium datasets
    6. Interpretable results

Input:
    training/dataset.csv (from export_training_data.py)

Output:
    training/scoring_model.pkl (trained model)
    training/feature_scaler.pkl (optional scaler)

Author: InterviewAI Team
Date: 2026-02-17
========================================
"""

import os
import sys
import logging
import warnings
from pathlib import Path
from typing import Tuple, Dict, Any, List

import numpy as np
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)

# Import our feature extractor
from feature_extractor import extract_features, get_feature_names

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")

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

# File paths
TRAINING_DIR = Path(__file__).parent
DATASET_PATH = TRAINING_DIR / "dataset.csv"
MODEL_PATH = TRAINING_DIR / "scoring_model.pkl"
SCALER_PATH = TRAINING_DIR / "feature_scaler.pkl"

# Model hyperparameters
RANDOM_STATE = 42       # For reproducibility
TEST_SIZE = 0.2         # 80% train, 20% test
N_ESTIMATORS = 100      # Number of trees in forest
MAX_DEPTH = 10          # Prevent overfitting
MIN_SAMPLES_SPLIT = 5   # Minimum samples to split a node
MIN_SAMPLES_LEAF = 2    # Minimum samples in leaf node


# ========================================
# DATA LOADING
# ========================================

def load_dataset(path: Path) -> pd.DataFrame:
    """
    Load the training dataset from CSV.
    
    Args:
        path: Path to dataset.csv
        
    Returns:
        DataFrame with training data
        
    Raises:
        FileNotFoundError if dataset doesn't exist
    """
    if not path.exists():
        raise FileNotFoundError(
            f"❌ Dataset not found at: {path}\n"
            f"   Run export_training_data.py first!"
        )
    
    df = pd.read_csv(path)
    logger.info(f"📂 Loaded dataset: {len(df)} records")
    
    return df


# ========================================
# FEATURE MATRIX CONSTRUCTION
# ========================================

def build_feature_matrix(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build feature matrix X and target vector y.
    
    Process:
        1. For each row, extract features from question+answer
        2. Collect all feature vectors into matrix X
        3. Extract score column as target y
        
    Args:
        df: DataFrame with question_text, answer_text, score columns
        
    Returns:
        Tuple of (X, y) where:
            X: Feature matrix (n_samples, n_features)
            y: Target scores (n_samples,)
    """
    logger.info("🔧 Extracting features from dataset...")
    
    feature_list = []
    scores = []
    
    # Progress tracking
    total = len(df)
    
    for idx, row in df.iterrows():
        # Extract features
        features = extract_features(
            question=row["question_text"],
            answer=row["answer_text"]
        )
        feature_list.append(features)
        scores.append(row["score"])
        
        # Progress update every 100 rows
        if (idx + 1) % 100 == 0:
            logger.info(f"   Processed {idx + 1}/{total} records...")
    
    # Convert to numpy arrays
    X = np.array(feature_list)
    y = np.array(scores)
    
    logger.info(f"✅ Feature matrix shape: {X.shape}")
    logger.info(f"✅ Target vector shape: {y.shape}")
    
    return X, y


# ========================================
# MODEL TRAINING
# ========================================

def train_random_forest(
    X_train: np.ndarray,
    y_train: np.ndarray
) -> RandomForestRegressor:
    """
    Train Random Forest Regressor.
    
    Hyperparameters explained:
        - n_estimators: More trees = more stable predictions (but slower)
        - max_depth: Limits tree depth to prevent overfitting
        - min_samples_split: Prevents splits on tiny groups
        - min_samples_leaf: Ensures leaves have enough samples
        - random_state: Makes results reproducible
        
    Args:
        X_train: Training feature matrix
        y_train: Training target scores
        
    Returns:
        Trained RandomForestRegressor
    """
    logger.info("🌳 Training Random Forest model...")
    logger.info(f"   n_estimators: {N_ESTIMATORS}")
    logger.info(f"   max_depth: {MAX_DEPTH}")
    logger.info(f"   min_samples_split: {MIN_SAMPLES_SPLIT}")
    logger.info(f"   min_samples_leaf: {MIN_SAMPLES_LEAF}")
    
    model = RandomForestRegressor(
        n_estimators=N_ESTIMATORS,
        max_depth=MAX_DEPTH,
        min_samples_split=MIN_SAMPLES_SPLIT,
        min_samples_leaf=MIN_SAMPLES_LEAF,
        random_state=RANDOM_STATE,
        n_jobs=-1,  # Use all CPU cores
        verbose=0
    )
    
    model.fit(X_train, y_train)
    
    logger.info("✅ Model training complete!")
    
    return model


# ========================================
# MODEL EVALUATION
# ========================================

def evaluate_model(
    model: RandomForestRegressor,
    X_test: np.ndarray,
    y_test: np.ndarray
) -> Dict[str, float]:
    """
    Evaluate model performance on test set.
    
    Metrics:
        - MAE (Mean Absolute Error): Average error magnitude
        - RMSE (Root Mean Squared Error): Penalizes large errors
        - R² (Coefficient of Determination): Variance explained
        
    Args:
        model: Trained model
        X_test: Test features
        y_test: True test scores
        
    Returns:
        Dictionary of metric names to values
    """
    logger.info("📊 Evaluating model performance...")
    
    # Get predictions
    y_pred = model.predict(X_test)
    
    # Calculate metrics
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)
    
    metrics = {
        "MAE": mae,
        "RMSE": rmse,
        "R2": r2
    }
    
    return metrics


def perform_cross_validation(
    model: RandomForestRegressor,
    X: np.ndarray,
    y: np.ndarray,
    cv: int = 5
) -> Dict[str, float]:
    """
    Perform k-fold cross-validation.
    
    Why cross-validation?
        - More robust estimate of model performance
        - Uses all data for both training and testing
        - Reduces variance in evaluation
        
    Args:
        model: Model to evaluate
        X: Full feature matrix
        y: Full target vector
        cv: Number of folds
        
    Returns:
        Dictionary with mean and std of scores
    """
    logger.info(f"🔄 Performing {cv}-fold cross-validation...")
    
    # scikit-learn's cross_val_score uses negative MSE by default
    # We use neg_mean_absolute_error for interpretability
    scores = cross_val_score(
        model, X, y,
        cv=cv,
        scoring="neg_mean_absolute_error"
    )
    
    # Convert negative MAE to positive
    mae_scores = -scores
    
    return {
        "CV_MAE_mean": mae_scores.mean(),
        "CV_MAE_std": mae_scores.std()
    }


def print_evaluation_report(
    metrics: Dict[str, float],
    cv_metrics: Dict[str, float]
) -> None:
    """
    Print a formatted evaluation report.
    """
    print("\n" + "=" * 60)
    print("📊 MODEL EVALUATION REPORT")
    print("=" * 60)
    
    print("\n📈 TEST SET METRICS:")
    print("-" * 40)
    print(f"   Mean Absolute Error (MAE): {metrics['MAE']:.3f}")
    print(f"   Root Mean Squared Error (RMSE): {metrics['RMSE']:.3f}")
    print(f"   R² Score: {metrics['R2']:.3f}")
    
    print("\n📈 CROSS-VALIDATION METRICS (5-fold):")
    print("-" * 40)
    print(f"   Mean MAE: {cv_metrics['CV_MAE_mean']:.3f} ± {cv_metrics['CV_MAE_std']:.3f}")
    
    print("\n📝 INTERPRETATION:")
    print("-" * 40)
    
    # MAE interpretation
    if metrics['MAE'] < 1.0:
        print("   ✅ MAE < 1.0: Excellent! Predictions within 1 point on average.")
    elif metrics['MAE'] < 1.5:
        print("   ✓ MAE < 1.5: Good. Predictions within 1.5 points on average.")
    elif metrics['MAE'] < 2.0:
        print("   ⚠️ MAE < 2.0: Acceptable, but room for improvement.")
    else:
        print("   ❌ MAE >= 2.0: Model needs improvement. Consider more features.")
    
    # R² interpretation
    if metrics['R2'] > 0.7:
        print("   ✅ R² > 0.7: Model explains most variance in scores.")
    elif metrics['R2'] > 0.5:
        print("   ✓ R² > 0.5: Model captures moderate variance.")
    else:
        print("   ⚠️ R² < 0.5: Consider adding more features or data.")
    
    print("\n" + "=" * 60)


# ========================================
# FEATURE IMPORTANCE
# ========================================

def analyze_feature_importance(
    model: RandomForestRegressor,
    feature_names: List[str]
) -> pd.DataFrame:
    """
    Analyze and rank feature importance.
    
    Random Forest provides built-in feature importance based on:
        - Mean decrease in impurity (Gini importance)
        - How much each feature reduces prediction error
        
    Args:
        model: Trained Random Forest model
        feature_names: List of feature names
        
    Returns:
        DataFrame with features ranked by importance
    """
    # Get importance scores
    importances = model.feature_importances_
    
    # Create DataFrame
    importance_df = pd.DataFrame({
        "Feature": feature_names,
        "Importance": importances
    })
    
    # Sort by importance (descending)
    importance_df = importance_df.sort_values(
        by="Importance",
        ascending=False
    ).reset_index(drop=True)
    
    # Add rank
    importance_df["Rank"] = range(1, len(importance_df) + 1)
    
    return importance_df


def print_feature_importance(importance_df: pd.DataFrame) -> None:
    """
    Print feature importance rankings.
    """
    print("\n" + "=" * 60)
    print("🎯 FEATURE IMPORTANCE RANKING")
    print("=" * 60)
    print("\n   (Higher importance = more influence on predictions)\n")
    
    for _, row in importance_df.iterrows():
        bar_length = int(row["Importance"] * 50)
        bar = "█" * bar_length
        print(f"   {row['Rank']}. {row['Feature']:25s} {row['Importance']:.3f} {bar}")
    
    print("\n" + "=" * 60)


# ========================================
# MODEL PERSISTENCE
# ========================================

def save_model(
    model: RandomForestRegressor,
    model_path: Path,
    scaler: StandardScaler = None,
    scaler_path: Path = None
) -> None:
    """
    Save trained model (and optional scaler) to disk.
    
    Uses joblib for efficient serialization of sklearn objects.
    
    Args:
        model: Trained model
        model_path: Path to save model
        scaler: Optional fitted scaler
        scaler_path: Path to save scaler
    """
    # Ensure output directory exists
    model_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save model
    joblib.dump(model, model_path)
    logger.info(f"💾 Model saved to: {model_path}")
    
    # Save scaler if provided
    if scaler is not None and scaler_path is not None:
        joblib.dump(scaler, scaler_path)
        logger.info(f"💾 Scaler saved to: {scaler_path}")


def load_model(model_path: Path) -> RandomForestRegressor:
    """
    Load a trained model from disk.
    
    Args:
        model_path: Path to saved model
        
    Returns:
        Loaded RandomForestRegressor
    """
    if not model_path.exists():
        raise FileNotFoundError(f"❌ Model not found at: {model_path}")
    
    model = joblib.load(model_path)
    logger.info(f"📂 Model loaded from: {model_path}")
    
    return model


# ========================================
# PREDICTION FUNCTION (for integration)
# ========================================

def predict_score(
    question: str,
    answer: str,
    model: RandomForestRegressor = None
) -> float:
    """
    Predict score for a single question-answer pair.
    
    This function can be called from answer_evaluator.py
    after integration.
    
    Args:
        question: Interview question
        answer: Candidate's answer
        model: Trained model (loads from disk if None)
        
    Returns:
        Predicted score (1-10)
    """
    # Load model if not provided
    if model is None:
        model = load_model(MODEL_PATH)
    
    # Extract features
    features = extract_features(question, answer)
    X = np.array([features])
    
    # Predict
    score = model.predict(X)[0]
    
    # Clamp to valid range [1, 10]
    score = max(1.0, min(10.0, score))
    
    return round(score, 1)


# ========================================
# MAIN TRAINING PIPELINE
# ========================================

def main():
    """
    Main training pipeline.
    
    Steps:
        1. Load dataset
        2. Build feature matrix
        3. Split train/test
        4. Train model
        5. Evaluate
        6. Feature importance analysis
        7. Save model
    """
    print("\n" + "=" * 60)
    print("🚀 INTERVIEW ANSWER SCORING MODEL TRAINING")
    print("   Random Forest Regressor")
    print("=" * 60 + "\n")
    
    try:
        # ========================================
        # STEP 1: Load Data
        # ========================================
        logger.info("📥 Step 1: Loading dataset...")
        df = load_dataset(DATASET_PATH)
        
        # Quick data summary
        print(f"\n📊 Dataset Summary:")
        print(f"   Total samples: {len(df)}")
        print(f"   Score range: {df['score'].min():.1f} - {df['score'].max():.1f}")
        print(f"   Score mean: {df['score'].mean():.2f}")
        
        # ========================================
        # STEP 2: Build Features
        # ========================================
        logger.info("\n🔧 Step 2: Building feature matrix...")
        X, y = build_feature_matrix(df)
        
        # ========================================
        # STEP 3: Train/Test Split
        # ========================================
        logger.info("\n✂️ Step 3: Splitting data...")
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE
        )
        logger.info(f"   Training samples: {len(X_train)}")
        logger.info(f"   Test samples: {len(X_test)}")
        
        # ========================================
        # STEP 4: Train Model
        # ========================================
        logger.info("\n🌳 Step 4: Training model...")
        model = train_random_forest(X_train, y_train)
        
        # ========================================
        # STEP 5: Evaluate
        # ========================================
        logger.info("\n📊 Step 5: Evaluating model...")
        metrics = evaluate_model(model, X_test, y_test)
        cv_metrics = perform_cross_validation(model, X, y)
        
        print_evaluation_report(metrics, cv_metrics)
        
        # ========================================
        # STEP 6: Feature Importance
        # ========================================
        logger.info("\n🎯 Step 6: Analyzing feature importance...")
        feature_names = get_feature_names()
        importance_df = analyze_feature_importance(model, feature_names)
        
        print_feature_importance(importance_df)
        
        # ========================================
        # STEP 7: Save Model
        # ========================================
        logger.info("\n💾 Step 7: Saving model...")
        save_model(model, MODEL_PATH)
        
        # ========================================
        # FINAL SUMMARY
        # ========================================
        print("\n" + "=" * 60)
        print("✅ TRAINING COMPLETE!")
        print("=" * 60)
        print(f"\n   📁 Model saved: {MODEL_PATH}")
        print(f"   📊 Test MAE: {metrics['MAE']:.3f}")
        print(f"   📈 Test R²: {metrics['R2']:.3f}")
        print("\n   Next step: Integrate with answer_evaluator.py")
        print("   (See documentation for integration guide)")
        print("\n" + "=" * 60)
        
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
