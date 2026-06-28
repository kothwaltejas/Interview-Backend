-- SQL Migration: Create eval_stats_log table for observability
-- Run this in your Supabase SQL Editor at https://app.supabase.com

CREATE TABLE IF NOT EXISTS eval_stats_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recorded_at TIMESTAMPTZ DEFAULT NOW(),
    total INTEGER,
    fallback INTEGER,
    dataset_match INTEGER,
    strong_match INTEGER,
    llm_unavailable INTEGER DEFAULT 0
);
