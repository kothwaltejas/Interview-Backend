"""
Extended Database Schema for Per-Answer Evaluation Integration

This file contains SQL extensions to add evaluation fields to existing
interview session and answer tables.

Usage:
1. Run in Supabase SQL Editor at https://app.supabase.com
2. Copy the SQL statements below and paste into SQL Editor
3. Click "Run"

These extensions add per-answer evaluation storage to the interview flow.
"""

-- ═══════════════════════════════════════════════════════════════════════════
-- EXTEND SESSIONS TABLE (if it exists)
-- ═══════════════════════════════════════════════════════════════════════════
-- Add evaluation summary fields to track overall performance

ALTER TABLE IF EXISTS sessions ADD COLUMN IF NOT EXISTS (
  -- Evaluation summary from per-answer evaluations
  evaluation_summary JSONB,
  
  -- Overall metrics
  overall_score NUMERIC(3, 2),
  performance_tier VARCHAR(20),  -- Outstanding, Strong, Solid, Developing, Beginning
  consistency_score NUMERIC(3, 2),  -- 0-1, how consistent are answers
  
  -- Aggregate weak areas from all answers
  weak_areas_summary TEXT[],
  strength_areas_summary TEXT[],
  
  -- Category averages
  average_score_technical NUMERIC(3, 2),
  average_score_clarity NUMERIC(3, 2),
  average_score_communication NUMERIC(3, 2),
  average_score_confidence NUMERIC(3, 2),
  
  -- Additional coaching summary
  top_improvement_focus TEXT[],
  coaching_summary TEXT
);

-- ═══════════════════════════════════════════════════════════════════════════
-- EXTEND ANSWERS TABLE (if it exists)
-- ═══════════════════════════════════════════════════════════════════════════
-- Add per-answer evaluation fields

ALTER TABLE IF EXISTS answers ADD COLUMN IF NOT EXISTS (
  -- Evaluation data
  evaluation_json JSONB,  -- Full evaluation object
  
  -- Structured scores
  scores JSONB,  -- {technical_accuracy, clarity, communication, confidence}
  
  -- Feedback components
  feedback TEXT,
  weak_areas TEXT[],      -- Array of identified weak areas
  strengths TEXT[],       -- Array of identified strengths
  improved_answer TEXT,   -- Better version of the answer
  
  -- Coaching
  coaching_tips TEXT[],
  
  -- Metadata
  evaluation_score NUMERIC(3, 2),  -- Average score
  evaluation_timestamp TIMESTAMP DEFAULT NOW(),
  
  -- Context
  dataset_matched BOOLEAN DEFAULT FALSE,
  matched_question_category VARCHAR
);

-- Create indexes for evaluation queries
CREATE INDEX IF NOT EXISTS idx_answers_evaluation_score 
  ON answers(evaluation_score DESC);

CREATE INDEX IF NOT EXISTS idx_answers_weak_areas
  ON answers USING GIN(weak_areas);

CREATE INDEX IF NOT EXISTS idx_answers_dataset_matched
  ON answers(dataset_matched);


-- ═══════════════════════════════════════════════════════════════════════════
-- NEW TABLE: Per-Answer Evaluations (Alternative to extending answers)
-- ═══════════════════════════════════════════════════════════════════════════
-- Use if you prefer to keep evaluations separate from answers

CREATE TABLE IF NOT EXISTS answer_evaluations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- References
  answer_id UUID REFERENCES answers(id) ON DELETE CASCADE,
  session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  
  -- Question context
  question_number INTEGER,
  question_text TEXT,
  category VARCHAR,
  
  -- Answer data
  answer_text TEXT NOT NULL,
  
  -- Evaluation scores
  scores JSONB,  -- {technical_accuracy: X, clarity: X, communication: X, confidence: X}
  average_score NUMERIC(3, 2),
  
  -- Feedback
  feedback TEXT,
  strengths TEXT[],
  weaknesses TEXT[],
  weak_areas TEXT[],
  improved_answer TEXT,
  coaching_tips TEXT[],
  
  -- Context
  dataset_matched BOOLEAN DEFAULT FALSE,
  matched_dataset_category VARCHAR,
  
  -- Full evaluation (for reference)
  evaluation_json JSONB,
  
  -- Timestamps
  created_at TIMESTAMP DEFAULT NOW(),
  evaluated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_answer_evaluations_session
  ON answer_evaluations(session_id);

CREATE INDEX IF NOT EXISTS idx_answer_evaluations_user
  ON answer_evaluations(user_id);

CREATE INDEX IF NOT EXISTS idx_answer_evaluations_score
  ON answer_evaluations(average_score DESC);

CREATE INDEX IF NOT EXISTS idx_answer_evaluations_weak_areas
  ON answer_evaluations USING GIN(weak_areas);


-- ═══════════════════════════════════════════════════════════════════════════
-- VIEWS FOR ANALYTICS
-- ═══════════════════════════════════════════════════════════════════════════

-- Session evaluation summary
CREATE OR REPLACE VIEW session_evaluation_summary AS
SELECT
  s.id AS session_id,
  s.user_id,
  s.target_role,
  s.experience_level,
  COUNT(a.id) AS total_answers,
  AVG(a.evaluation_score::numeric) AS average_score,
  MAX(a.evaluation_score::numeric) AS best_answer_score,
  MIN(a.evaluation_score::numeric) AS worst_answer_score,
  ARRAY_AGG(DISTINCT UNNEST(a.weak_areas)) FILTER (WHERE a.weak_areas IS NOT NULL) AS weak_areas_list,
  s.overall_score,
  s.performance_tier,
  s.consistency_score
FROM sessions s
LEFT JOIN answers a ON s.id = a.session_id
GROUP BY s.id, s.user_id, s.target_role, s.experience_level;

-- User progress tracking
CREATE OR REPLACE VIEW user_evaluation_progress AS
SELECT
  s.user_id,
  s.target_role,
  COUNT(DISTINCT s.id) AS total_sessions,
  AVG(s.overall_score) AS avg_session_score,
  MAX(s.overall_score) AS best_session_score,
  COUNT(DISTINCT a.id) AS total_answers_evaluated,
  ARRAY_AGG(DISTINCT UNNEST(a.weak_areas)) FILTER (WHERE a.weak_areas IS NOT NULL) AS persistent_weak_areas
FROM sessions s
LEFT JOIN answers a ON s.id = a.session_id
WHERE s.user_id IS NOT NULL
GROUP BY s.user_id, s.target_role;

-- Weak areas frequency (for insights)
CREATE OR REPLACE VIEW weak_areas_frequency AS
SELECT
  UNNEST(weak_areas) AS weak_area,
  COUNT(*) AS frequency,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM answers), 2) AS percentage
FROM answers
WHERE weak_areas IS NOT NULL
GROUP BY weak_area
ORDER BY frequency DESC;

-- Category performance (for insights)
CREATE OR REPLACE VIEW category_performance AS
SELECT
  category,
  COUNT(*) AS total_answers,
  ROUND(AVG(evaluation_score::numeric), 2) AS avg_score,
  ROUND(MAX(evaluation_score::numeric), 2) AS best_score,
  ROUND(MIN(evaluation_score::numeric), 2) AS worst_score
FROM answers
WHERE category IS NOT NULL AND evaluation_score IS NOT NULL
GROUP BY category
ORDER BY avg_score DESC;


-- ═══════════════════════════════════════════════════════════════════════════
-- ROW-LEVEL SECURITY (RLS) POLICIES
-- ═══════════════════════════════════════════════════════════════════════════
-- Ensure users can only see their own data

-- Enable RLS if not already enabled
ALTER TABLE IF EXISTS answer_evaluations ENABLE ROW LEVEL SECURITY;

-- Users can only see their own evaluations
CREATE POLICY answer_evaluations_user_isolation 
  ON answer_evaluations 
  FOR SELECT 
  USING (auth.uid() = user_id OR user_id IS NULL);

CREATE POLICY answer_evaluations_insert_own 
  ON answer_evaluations 
  FOR INSERT 
  WITH CHECK (auth.uid() = user_id);

-- Admin can view all (if admin role exists)
CREATE POLICY answer_evaluations_admin 
  ON answer_evaluations 
  FOR ALL 
  USING (
    EXISTS (
      SELECT 1 FROM auth.users 
      WHERE id = auth.uid() 
      AND (raw_user_meta_data->>'role' = 'admin')
    )
  );

