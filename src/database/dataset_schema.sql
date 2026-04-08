"""
Supabase Schema Setup for Generated Datasets

This file contains SQL statements to create tables for storing
generated interview training datasets.

Usage:
1. Run in Supabase SQL Editor at https://app.supabase.com
2. OR use: supabase db push (if using migrations)
3. OR run programmatically via database_setup.py

Tables Created:
- generated_datasets: Stores question-answer-evaluation tuples
- dataset_generation_logs: Tracks generation runs
"""

# SQL for Supabase (copy-paste directly into SQL Editor)

SQL_SCHEMA = """
-- ═══════════════════════════════════════════════════════════════════════════
-- GENERATED DATASETS TABLE
-- ═══════════════════════════════════════════════════════════════════════════
-- Stores training data: questions with ideal/average/poor answers and evaluations

CREATE TABLE IF NOT EXISTS generated_datasets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Question and context
  question TEXT NOT NULL,
  question_metadata JSONB DEFAULT '{}',
  target_role VARCHAR DEFAULT 'Software Engineer',
  experience_level VARCHAR DEFAULT '3-5 years',
  interview_type VARCHAR DEFAULT 'Technical',
  
  -- Ideal answer (excellent candidate)
  ideal_answer TEXT,
  ideal_scores JSONB,  -- {technical_accuracy, clarity, communication, confidence}
  
  -- Average answer (typical candidate)
  average_answer TEXT,
  average_scores JSONB,
  
  -- Poor answer (weak candidate)
  poor_answer TEXT,
  poor_scores JSONB,
  
  -- Metadata
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  source VARCHAR DEFAULT 'generated',  -- 'generated', 'manual', 'imported'
  
  -- Tracking
  generation_run_id UUID REFERENCES dataset_generation_runs(id) ON DELETE SET NULL,
  
  CONSTRAINT scores_validation CHECK (ideal_scores IS NULL OR (
    (ideal_scores->>'technical_accuracy')::int >= 1 AND
    (ideal_scores->>'technical_accuracy')::int <= 10
  ))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_generated_datasets_created_at 
  ON generated_datasets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_generated_datasets_role 
  ON generated_datasets(target_role);
CREATE INDEX IF NOT EXISTS idx_generated_datasets_experience 
  ON generated_datasets(experience_level);
CREATE INDEX IF NOT EXISTS idx_generated_datasets_source 
  ON generated_datasets(source);

-- For full-text search on questions
CREATE INDEX IF NOT EXISTS idx_generated_datasets_question_text 
  ON generated_datasets USING GIN(to_tsvector('english', question));

---

-- ═══════════════════════════════════════════════════════════════════════════
-- DATASET GENERATION LOGS TABLE
-- ═══════════════════════════════════════════════════════════════════════════
-- Tracks all dataset generation runs

CREATE TABLE IF NOT EXISTS dataset_generation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Generation parameters
  total_questions INTEGER NOT NULL,
  batch_size INTEGER DEFAULT 10,
  
  -- Results
  successful_entries INTEGER DEFAULT 0,
  failed_entries INTEGER DEFAULT 0,
  
  -- Timing
  started_at TIMESTAMP DEFAULT NOW(),
  completed_at TIMESTAMP,
  duration_seconds INTEGER GENERATED ALWAYS AS (
    EXTRACT(EPOCH FROM (completed_at - started_at))::int
  ) STORED,
  
  -- File output
  output_file VARCHAR,
  data_size_mb DECIMAL(10, 2),
  
  -- Status
  status VARCHAR CHECK (status IN ('running', 'completed', 'failed')),
  error_message TEXT,
  
  -- Metadata
  created_by VARCHAR,
  notes TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_generation_runs_status 
  ON dataset_generation_runs(status);
CREATE INDEX IF NOT EXISTS idx_generation_runs_completed_at 
  ON dataset_generation_runs(completed_at DESC);

---

-- ═══════════════════════════════════════════════════════════════════════════
-- DATASET STATISTICS TABLE (Materialized View)
-- ═══════════════════════════════════════════════════════════════════════════
-- Pre-computed statistics for dashboard

CREATE TABLE IF NOT EXISTS dataset_statistics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Aggregated metrics
  total_questions_in_dataset INTEGER,
  total_entries INTEGER,
  
  -- Average scores across all entries
  avg_ideal_technical_accuracy DECIMAL(3, 2),
  avg_ideal_clarity DECIMAL(3, 2),
  avg_ideal_communication DECIMAL(3, 2),
  avg_ideal_confidence DECIMAL(3, 2),
  
  avg_average_technical_accuracy DECIMAL(3, 2),
  avg_average_clarity DECIMAL(3, 2),
  avg_average_communication DECIMAL(3, 2),
  avg_average_confidence DECIMAL(3, 2),
  
  avg_poor_technical_accuracy DECIMAL(3, 2),
  avg_poor_clarity DECIMAL(3, 2),
  avg_poor_communication DECIMAL(3, 2),
  avg_poor_confidence DECIMAL(3, 2),
  
  -- Distribution by role
  roles_covered JSONB,  -- {role: count, ...}
  experience_levels_covered JSONB,
  
  -- Last updated
  computed_at TIMESTAMP DEFAULT NOW(),
  
  CONSTRAINT single_row CHECK (id = '00000000-0000-0000-0000-000000000001'::uuid)
);

---

-- ═══════════════════════════════════════════════════════════════════════════
-- FEATURE EXTRACTION TABLE (for ML training)
-- ═══════════════════════════════════════════════════════════════════════════
-- Pre-computed features for ML models

CREATE TABLE IF NOT EXISTS answer_features (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  dataset_entry_id UUID NOT NULL REFERENCES generated_datasets(id) ON DELETE CASCADE,
  
  -- Answer type
  answer_type VARCHAR NOT NULL CHECK (answer_type IN ('ideal', 'average', 'poor')),
  
  -- Text features
  answer_length INTEGER,
  word_count INTEGER,
  sentence_count INTEGER,
  avg_sentence_length DECIMAL(5, 2),
  unique_words INTEGER,
  
  -- Linguistic features
  lexical_diversity DECIMAL(3, 2),
  avg_word_length DECIMAL(3, 2),
  
  -- Timing features (if available)
  time_taken_seconds INTEGER,
  time_vs_expected_ratio DECIMAL(5, 2),
  
  -- Context matching
  question_relevance_score DECIMAL(3, 2),
  resume_relevance_score DECIMAL(3, 2),
  technical_terms_count INTEGER,
  technical_terms_ratio DECIMAL(3, 2),
  
  -- Evaluation scores (from dataset)
  technical_accuracy INTEGER,
  clarity INTEGER,
  communication INTEGER,
  confidence INTEGER,
  
  -- Aggregate score
  aggregate_score DECIMAL(3, 2),
  
  created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for ML queries
CREATE INDEX IF NOT EXISTS idx_answer_features_dataset_id 
  ON answer_features(dataset_entry_id);
CREATE INDEX IF NOT EXISTS idx_answer_features_answer_type 
  ON answer_features(answer_type);
CREATE INDEX IF NOT EXISTS idx_answer_features_aggregate_score 
  ON answer_features(aggregate_score);

---

-- ═══════════════════════════════════════════════════════════════════════════
-- ENABLE ROW-LEVEL SECURITY (if using auth)
-- ═══════════════════════════════════════════════════════════════════════════

-- Allow authenticated users to view datasets
ALTER TABLE generated_datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE dataset_generation_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view generated datasets" 
  ON generated_datasets FOR SELECT 
  USING (true);

CREATE POLICY "Only admins can insert datasets" 
  ON generated_datasets FOR INSERT 
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM auth.users
      WHERE auth.uid() = id 
      AND raw_user_meta_data->>'role' = 'admin'
    )
  );

---

-- ═══════════════════════════════════════════════════════════════════════════
-- HELPER FUNCTIONS
-- ═══════════════════════════════════════════════════════════════════════════

-- Function to calculate average scores
CREATE OR REPLACE FUNCTION get_dataset_statistics()
RETURNS TABLE (
  total_entries BIGINT,
  avg_ideal_score DECIMAL,
  avg_average_score DECIMAL,
  avg_poor_score DECIMAL,
  top_questions TEXT[]
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    COUNT(*)::BIGINT,
    (AVG((ideal_scores->>'technical_accuracy')::int + 
          (ideal_scores->>'clarity')::int + 
          (ideal_scores->>'communication')::int + 
          (ideal_scores->>'confidence')::int) / 4)::DECIMAL,
    (AVG((average_scores->>'technical_accuracy')::int + 
          (average_scores->>'clarity')::int + 
          (average_scores->>'communication')::int + 
          (average_scores->>'confidence')::int) / 4)::DECIMAL,
    (AVG((poor_scores->>'technical_accuracy')::int + 
          (poor_scores->>'clarity')::int + 
          (poor_scores->>'communication')::int + 
          (poor_scores->>'confidence')::int) / 4)::DECIMAL,
    ARRAY_AGG(DISTINCT question ORDER BY question LIMIT 5)
  FROM generated_datasets;
END;
$$ LANGUAGE plpgsql;

---

-- ═══════════════════════════════════════════════════════════════════════════
-- SAMPLE QUERIES FOR TESTING
-- ═══════════════════════════════════════════════════════════════════════════

-- Count total dataset entries
-- SELECT COUNT(*) as total_entries, target_role, experience_level
-- FROM generated_datasets
-- GROUP BY target_role, experience_level;

-- Get dataset statistics
-- SELECT * FROM get_dataset_statistics();

-- Find entries by role
-- SELECT id, question, target_role 
-- FROM generated_datasets 
-- WHERE target_role = 'Senior Backend Engineer'
-- LIMIT 10;

-- Search questions by keyword
-- SELECT id, question 
-- FROM generated_datasets 
-- WHERE to_tsvector('english', question) @@ plainto_tsquery('english', 'database')
-- LIMIT 10;

-- Get recent generation runs
-- SELECT id, total_questions, successful_entries, completed_at, status
-- FROM dataset_generation_runs
-- ORDER BY completed_at DESC
-- LIMIT 10;
"""

if __name__ == "__main__":
    print(SQL_SCHEMA)
    print("\n✅ To use this schema:")
    print("1. Copy the SQL above")
    print("2. Go to https://app.supabase.com")
    print("3. Open SQL Editor in your project")
    print("4. Paste and execute")
