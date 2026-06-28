-- Multi-Sector Evaluation Schema Extension
-- Adds voice and camera analysis columns to support 3-sector evaluation:
--   1. Text answer (existing)
--   2. Voice analysis (fluency, pace, filler words)
--   3. Camera analysis (attention, presence, emotion)

-- Add voice and camera metrics to interview_answers
ALTER TABLE interview_answers
  ADD COLUMN IF NOT EXISTS voice_metrics JSONB,
  ADD COLUMN IF NOT EXISTS camera_metrics JSONB;

-- Add multi-sector scores to answer_evaluations
ALTER TABLE answer_evaluations
  ADD COLUMN IF NOT EXISTS voice_score FLOAT,
  ADD COLUMN IF NOT EXISTS camera_score FLOAT,
  ADD COLUMN IF NOT EXISTS composite_score FLOAT,
  ADD COLUMN IF NOT EXISTS voice_metrics JSONB,
  ADD COLUMN IF NOT EXISTS camera_metrics JSONB;

-- Add composite score to interview_sessions for summary
ALTER TABLE interview_sessions
  ADD COLUMN IF NOT EXISTS average_composite_score FLOAT;
