"""
Supabase Schema Setup for Evaluation Results

This file contains SQL statements to create tables for storing
evaluation results from the enhanced evaluation system.

Usage:
1. Run in Supabase SQL Editor at https://app.supabase.com
2. Copy the SQL statements below and paste into SQL Editor
3. Click "Run"

Tables Created:
- evaluations: Stores individual answer evaluations
- evaluation_sessions: Tracks evaluation sessions for analytics
"""

-- ═══════════════════════════════════════════════════════════════════════════
-- EVALUATIONS TABLE
-- ═══════════════════════════════════════════════════════════════════════════
-- Stores individual answer evaluations with scores and feedback

CREATE TABLE IF NOT EXISTS evaluations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- User reference (optional - can be null for guest evaluations)
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  
  -- Question and answer
  question TEXT NOT NULL,
  answer_text TEXT NOT NULL,
  
  -- Context
  target_role VARCHAR DEFAULT 'Backend Engineer',
  experience_level VARCHAR DEFAULT 'Mid',
  interview_type VARCHAR DEFAULT 'Mixed',
  
  -- Evaluation scores (stored as JSONB)
  scores JSONB DEFAULT '{}', -- {technical_accuracy, clarity, communication, confidence}
  average_score NUMERIC(3,1),
  
  -- Feedback and results
  feedback TEXT,
  strengths TEXT[],  -- Array of strengths
  weaknesses TEXT[],  -- Array of weaknesses
  weak_areas TEXT[],  -- Array of weak areas (technical, clarity, communication, confidence)
  improved_answer TEXT,
  coaching_tips TEXT[],
  
  -- Metadata
  dataset_match BOOLEAN DEFAULT FALSE,
  comparison_enabled BOOLEAN DEFAULT FALSE,
  matched_question_category VARCHAR,
  
  -- Full evaluation JSON (for reference)
  evaluation_json JSONB DEFAULT '{}',
  
  -- Timestamps
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_evaluations_user_id 
  ON evaluations(user_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_created_at 
  ON evaluations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evaluations_target_role 
  ON evaluations(target_role);
CREATE INDEX IF NOT EXISTS idx_evaluations_average_score 
  ON evaluations(average_score DESC);
CREATE INDEX IF NOT EXISTS idx_evaluations_dataset_match 
  ON evaluations(dataset_match);

-- Full-text search on questions and answers
CREATE INDEX IF NOT EXISTS idx_evaluations_question_text 
  ON evaluations USING GIN(to_tsvector('english', question));


-- ═══════════════════════════════════════════════════════════════════════════
-- EVALUATION SESSIONS TABLE
-- ═══════════════════════════════════════════════════════════════════════════
-- Tracks evaluation sessions for analytics and progress tracking

CREATE TABLE IF NOT EXISTS evaluation_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- User reference
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  session_id VARCHAR UNIQUE,
  
  -- Session info
  total_evaluations INTEGER DEFAULT 0,
  completed_evaluations INTEGER DEFAULT 0,
  average_score NUMERIC(3,1),
  
  -- Weak areas summary
  common_weak_areas TEXT[],
  areas_needing_focus VARCHAR[],
  
  -- Progress
  in_progress BOOLEAN DEFAULT TRUE,
  started_at TIMESTAMP DEFAULT NOW(),
  completed_at TIMESTAMP,
  duration_seconds INTEGER,
  
  -- Metadata
  notes TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_evaluation_sessions_user_id 
  ON evaluation_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_sessions_in_progress 
  ON evaluation_sessions(in_progress);
CREATE INDEX IF NOT EXISTS idx_evaluation_sessions_created_at 
  ON evaluation_sessions(created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════════
-- ANALYTICS VIEW
-- ═══════════════════════════════════════════════════════════════════════════
-- Aggregate view for analytics

CREATE OR REPLACE VIEW evaluation_analytics AS
SELECT 
  user_id,
  COUNT(*) as total_evaluations,
  ROUND(AVG(average_score)::numeric, 1) as avg_score,
  MIN(average_score) as min_score,
  MAX(average_score) as max_score,
  COUNT(CASE WHEN dataset_match THEN 1 END) as dataset_matched_count,
  DATE(created_at) as evaluation_date,
  target_role,
  experience_level
FROM evaluations
WHERE user_id IS NOT NULL
GROUP BY user_id, DATE(created_at), target_role, experience_level;

-- ═══════════════════════════════════════════════════════════════════════════
-- WEAK AREAS SUMMARY VIEW
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW weak_areas_summary AS
SELECT 
  user_id,
  unnest(weak_areas) as weak_area,
  COUNT(*) as occurrence_count,
  ROUND(AVG(average_score)::numeric, 1) as avg_score_for_area,
  MAX(created_at) as last_occurrence
FROM evaluations
WHERE user_id IS NOT NULL AND weak_areas IS NOT NULL AND array_length(weak_areas, 1) > 0
GROUP BY user_id, unnest(weak_areas)
ORDER BY occurrence_count DESC;

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES (Enable security)
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE evaluations ENABLE ROW LEVEL SECURITY;

-- Users can see their own evaluations
CREATE POLICY "Users can view own evaluations" ON evaluations
  FOR SELECT USING (auth.uid() = user_id);

-- Users can insert their own evaluations
CREATE POLICY "Users can insert own evaluations" ON evaluations
  FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Service role can do anything
CREATE POLICY "Service role can manage" ON evaluations
  FOR ALL USING (current_setting('role') = 'authenticated');


-- ═══════════════════════════════════════════════════════════════════════════
-- SAMPLE QUERIES
-- ═══════════════════════════════════════════════════════════════════════════

-- Get user's top weak areas
-- SELECT * FROM weak_areas_summary WHERE user_id = '{user_id}' LIMIT 5;

-- Get user's evaluation progress
-- SELECT avg_score, target_role, COUNT(*) as count FROM evaluations 
-- WHERE user_id = '{user_id}' GROUP BY target_role;

-- Find evaluations with dataset matches
-- SELECT question, average_score, feedback FROM evaluations 
-- WHERE dataset_match = TRUE AND user_id = '{user_id}' ORDER BY created_at DESC;
