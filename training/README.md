# 🤖 Interview Answer Scoring Model

A supervised machine learning module for predicting interview answer scores (1-10) using Random Forest Regression.

---

## 📁 Project Structure

```
training/
├── export_training_data.py   # Step 1: Export data from Supabase
├── feature_extractor.py      # Step 2: Feature extraction functions
├── train_model.py            # Step 3: Model training pipeline
├── requirements.txt          # Python dependencies
├── README.md                 # This documentation
├── dataset.csv               # (Generated) Training data
└── scoring_model.pkl         # (Generated) Trained model
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd backend/training
pip install -r requirements.txt
```

### 2. Export Training Data

```bash
python export_training_data.py
```

This connects to Supabase and exports `interview_answers` data to `dataset.csv`.

### 3. Train the Model

```bash
python train_model.py
```

This trains a Random Forest model and saves it to `scoring_model.pkl`.

---

## 📖 Detailed Documentation

### 1️⃣ What is Random Forest?

**Random Forest** is an ensemble machine learning algorithm that builds multiple decision trees and combines their predictions.

**How it works:**
```
Training Data → Build 100 Trees → Each tree makes prediction → Average all predictions
```

**Why we chose Random Forest:**

| Advantage | Explanation |
|-----------|-------------|
| **No overfitting** | Multiple trees reduce variance |
| **Handles mixed features** | Works with different feature scales |
| **Feature importance** | Shows which features matter most |
| **Fast inference** | Quick predictions for production |
| **No scaling needed** | Tree-based methods don't need normalization |
| **Works with small data** | Robust even with few hundred samples |

**Visual representation:**
```
       [Decision Tree 1] → Score: 7.2
       [Decision Tree 2] → Score: 6.8       
Input →[Decision Tree 3] → Score: 7.5  → Average → Final: 7.1
       [Decision Tree 4] → Score: 6.9
       [...100 trees...] → ...
```

---

### 2️⃣ Features Used and Why

We extract 7 numerical features from each question-answer pair:

| # | Feature | Formula | Why It Matters |
|---|---------|---------|----------------|
| 1 | **word_count** | `len(words)` | Longer answers show more thought |
| 2 | **sentence_count** | `count(sentences)` | Multiple sentences = structured thinking |
| 3 | **avg_sentence_length** | `words / sentences` | Optimal: 10-25 words/sentence |
| 4 | **unique_word_ratio** | `unique / total` | Higher = richer vocabulary |
| 5 | **keyword_match_ratio** | `matched / question_keywords` | Shows answer relevance |
| 6 | **depth_indicator_score** | `count(technical_words)` | Signals expertise depth |
| 7 | **answer_length_normalized** | `(len - min) / (max - min)` | Normalized 0-1 scale |

**Depth Indicator Words:**
```python
["architecture", "optimized", "performance", "scalable", 
 "implemented", "designed", "algorithm", "because", 
 "therefore", "integrated", "deployed", "debugged"]
```

These words commonly appear in strong technical answers.

---

### 3️⃣ Evaluation Metrics Explained

#### MAE (Mean Absolute Error)
```
MAE = average(|predicted - actual|)
```
- **Meaning:** On average, how many points off are we?
- **Example:** MAE = 0.8 means predictions are ~0.8 points off on average
- **Good:** < 1.0 | **Acceptable:** < 1.5 | **Poor:** > 2.0

#### RMSE (Root Mean Squared Error)
```
RMSE = sqrt(average((predicted - actual)²))
```
- **Meaning:** Similar to MAE but penalizes large errors more
- **When high:** Model makes some very bad predictions
- **When low:** Predictions are consistently close

#### R² (Coefficient of Determination)
```
R² = 1 - (prediction_errors / total_variance)
```
- **Meaning:** How much variance does the model explain?
- **R² = 1.0:** Perfect predictions
- **R² = 0.7:** Explains 70% of score variation
- **R² = 0.0:** Model is no better than guessing the mean

**Interpretation Table:**

| R² Score | Quality | Next Steps |
|----------|---------|------------|
| > 0.8 | Excellent | Ready for production |
| 0.6 - 0.8 | Good | Consider more features |
| 0.4 - 0.6 | Moderate | Need more data/features |
| < 0.4 | Poor | Rethink feature design |

---

### 4️⃣ Future Integration with answer_evaluator.py

**Current Flow (LLM-only):**
```
Answer → GROQ LLM → Score (1-10)
```

**Proposed Hybrid Flow:**
```
Answer → [ML Model] → ML_Score
       → [GROQ LLM] → LLM_Score
       → Combine → Final_Score
```

**Integration Code (add to answer_evaluator.py):**

```python
from training.train_model import predict_score
from training.feature_extractor import extract_features

def hybrid_evaluate(question: str, answer: str, job_context: dict) -> dict:
    """
    Hybrid evaluation using both ML and LLM.
    
    Benefits:
        - ML provides instant baseline (no API call)
        - LLM provides nuanced feedback
        - Combine for robust scoring
    """
    # Step 1: ML score (instant, free)
    ml_score = predict_score(question, answer)
    
    # Step 2: LLM evaluation (slower, costs tokens)
    llm_result = evaluate_with_llm(question, answer, job_context)
    llm_score = llm_result.get("score", ml_score)
    
    # Step 3: Weighted combination (70% LLM, 30% ML)
    # LLM is more nuanced but ML prevents hallucination outliers
    final_score = (0.7 * llm_score) + (0.3 * ml_score)
    
    return {
        "score": round(final_score, 1),
        "ml_score": ml_score,
        "llm_score": llm_score,
        "feedback": llm_result.get("feedback"),
        "confidence": "high" if abs(ml_score - llm_score) < 1.5 else "moderate"
    }
```

**Fallback Strategy:**
```python
def evaluate_with_fallback(question: str, answer: str) -> float:
    """
    Use ML as fallback when LLM is unavailable (rate limits, errors).
    """
    try:
        return llm_evaluate(question, answer)
    except LLMRateLimitError:
        logger.warning("LLM rate limited, using ML fallback")
        return predict_score(question, answer)
```

---

### 5️⃣ Limitations of This Model

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **No semantic understanding** | Can't judge technical correctness | Combine with LLM |
| **Feature engineering dependent** | Quality depends on feature design | Iterate on features |
| **Needs training data** | Requires scored answers to learn | Collect more data over time |
| **Language-specific** | Only works for English | Add language features |
| **Score distribution bias** | If most scores are 5-7, model biased | Balance training data |
| **Can't explain reasoning** | Doesn't say WHY score is X | LLM provides explanations |

**What the model CAN'T do:**
- ❌ Understand if an answer is factually correct
- ❌ Detect subtle technical errors
- ❌ Understand sarcasm or tone
- ❌ Judge creativity or originality

**What the model CAN do:**
- ✅ Quickly assess answer structure
- ✅ Detect verbose vs. concise answers
- ✅ Measure vocabulary richness
- ✅ Check keyword relevance
- ✅ Identify depth indicators

---

### 6️⃣ How to Improve the Model

#### A. Add More Features

```python
# Semantic features (requires sentence-transformers)
def feature_semantic_similarity(question: str, answer: str) -> float:
    """Calculate cosine similarity between question and answer embeddings."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2')
    q_emb = model.encode(question)
    a_emb = model.encode(answer)
    return cosine_similarity(q_emb, a_emb)

# Category-specific features
def feature_category_encoded(category: str) -> List[float]:
    """One-hot encode question category."""
    categories = ["introduction", "technical", "behavioral", "scenario"]
    return [1.0 if category == c else 0.0 for c in categories]

# Difficulty-adjusted features
def feature_difficulty_weight(difficulty: str) -> float:
    """Weight based on question difficulty."""
    weights = {"easy": 0.8, "medium": 1.0, "hard": 1.2}
    return weights.get(difficulty, 1.0)
```

#### B. Use Better Models

```python
# Gradient Boosting (often better than RF)
from sklearn.ensemble import GradientBoostingRegressor
model = GradientBoostingRegressor(n_estimators=100, learning_rate=0.1)

# XGBoost (state-of-the-art for tabular data)
import xgboost as xgb
model = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1)

# Neural Network (for complex patterns)
from sklearn.neural_network import MLPRegressor
model = MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=500)
```

#### C. Collect More Data

```python
# Add data augmentation
def augment_answer(answer: str) -> List[str]:
    """Generate variations of answers for training."""
    variations = [
        answer,
        " ".join(answer.split()[:-2]),  # Slightly shorter
        answer + " Additionally, I ensured quality."  # Slightly longer
    ]
    return variations
```

#### D. Hyperparameter Tuning

```python
from sklearn.model_selection import GridSearchCV

param_grid = {
    'n_estimators': [50, 100, 200],
    'max_depth': [5, 10, 15, None],
    'min_samples_split': [2, 5, 10],
    'min_samples_leaf': [1, 2, 4]
}

grid_search = GridSearchCV(
    RandomForestRegressor(random_state=42),
    param_grid,
    cv=5,
    scoring='neg_mean_absolute_error'
)
grid_search.fit(X, y)

best_model = grid_search.best_estimator_
print(f"Best params: {grid_search.best_params_}")
```

---

## 📊 Expected Results

With sufficient training data (500+ samples), you should expect:

| Metric | Target | Meaning |
|--------|--------|---------|
| MAE | < 1.0 | Within 1 point on average |
| RMSE | < 1.3 | Few large errors |
| R² | > 0.6 | Explains 60%+ variance |

**Sample Output:**
```
📊 MODEL EVALUATION REPORT
========================================

📈 TEST SET METRICS:
   Mean Absolute Error (MAE): 0.847
   Root Mean Squared Error (RMSE): 1.102
   R² Score: 0.683

📈 CROSS-VALIDATION METRICS (5-fold):
   Mean MAE: 0.892 ± 0.065

🎯 FEATURE IMPORTANCE RANKING:
   1. word_count              0.285 ██████████████
   2. depth_indicator_score   0.198 █████████
   3. unique_word_ratio       0.156 ███████
   4. keyword_match_ratio     0.132 ██████
   5. avg_sentence_length     0.098 ████
   6. sentence_count          0.074 ███
   7. answer_length_normalized 0.057 ██
```

---

## 🔧 Troubleshooting

### No data in dataset.csv
```
Problem: "No valid records after filtering"
Solution: Run more interviews with scoring enabled first
```

### Model performs poorly (R² < 0.3)
```
Problem: Not enough training data or features
Solution: 
  1. Collect 500+ scored answers
  2. Add more features
  3. Check for data quality issues
```

### Import errors
```
Problem: "ModuleNotFoundError: No module named 'sklearn'"
Solution: pip install -r requirements.txt
```

---

## 📚 References

- [scikit-learn Random Forest](https://scikit-learn.org/stable/modules/ensemble.html#random-forests)
- [Feature Engineering for ML](https://www.oreilly.com/library/view/feature-engineering-for/9781491953235/)
- [ML Model Evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html)

---

*Last updated: February 2026*
