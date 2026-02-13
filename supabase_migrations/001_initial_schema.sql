-- =====================================================
-- INTERVU AI - SUPABASE DATABASE SCHEMA
-- Migration: 001_initial_schema.sql
-- =====================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- TABLE 1: user_profiles
-- Store additional user metadata
-- =====================================================

CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT,
    email TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index
CREATE INDEX idx_user_profiles_email ON user_profiles(email);

-- RLS Policies
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile"
    ON user_profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can insert own profile"
    ON user_profiles FOR INSERT
    WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON user_profiles FOR UPDATE
    USING (auth.uid() = id);

-- =====================================================
-- TABLE 2: resumes
-- Store uploaded resumes and parsed data
-- =====================================================

CREATE TABLE IF NOT EXISTS resumes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_url TEXT NOT NULL,
    file_size_bytes INTEGER,
    parsed_json JSONB NOT NULL,
    resume_summary TEXT,
    skills TEXT[],
    experience_years INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_resumes_user_id ON resumes(user_id);
CREATE INDEX idx_resumes_created_at ON resumes(created_at DESC);
CREATE INDEX idx_resumes_skills ON resumes USING GIN (skills);

-- RLS Policies
ALTER TABLE resumes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own resumes"
    ON resumes FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own resumes"
    ON resumes FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own resumes"
    ON resumes FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own resumes"
    ON resumes FOR DELETE
    USING (auth.uid() = user_id);

-- =====================================================
-- TABLE 3: interview_sessions
-- Store completed interview sessions only
-- =====================================================

CREATE TABLE IF NOT EXISTS interview_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    resume_id UUID REFERENCES resumes(id) ON DELETE SET NULL,
    target_role TEXT NOT NULL,
    experience_level TEXT NOT NULL,
    interview_type TEXT NOT NULL, -- technical / behavioral / mixed
    mode TEXT NOT NULL, -- conversational / standard
    total_questions INTEGER NOT NULL,
    answered_questions INTEGER NOT NULL,
    skipped_questions INTEGER NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    duration_seconds INTEGER,
    average_score NUMERIC(5,2), -- nullable (only for standard mode)
    performance_tier TEXT, -- excellent / good / average / needs_improvement
    overall_feedback JSONB, -- structured evaluation summary
    topics_covered TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_sessions_user_id ON interview_sessions(user_id);
CREATE INDEX idx_sessions_completed_at ON interview_sessions(completed_at DESC);
CREATE INDEX idx_sessions_target_role ON interview_sessions(target_role);
CREATE INDEX idx_sessions_performance_tier ON interview_sessions(performance_tier);
CREATE INDEX idx_sessions_topics ON interview_sessions USING GIN (topics_covered);

-- RLS Policies
ALTER TABLE interview_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own sessions"
    ON interview_sessions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own sessions"
    ON interview_sessions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own sessions"
    ON interview_sessions FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own sessions"
    ON interview_sessions FOR DELETE
    USING (auth.uid() = user_id);

-- =====================================================
-- TABLE 4: interview_answers
-- Store candidate answers for analytics
-- =====================================================

CREATE TABLE IF NOT EXISTS interview_answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    category TEXT, -- introduction / technical / project / behavioral / scenario
    difficulty TEXT, -- easy / medium / hard
    answer_text TEXT,
    is_skipped BOOLEAN DEFAULT FALSE,
    word_count INTEGER,
    duration_seconds INTEGER,
    score NUMERIC(5,2), -- nullable (only for standard mode)
    evaluation_summary JSONB, -- structured evaluation (not full LLM response)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_answers_session_id ON interview_answers(session_id);
CREATE INDEX idx_answers_category ON interview_answers(category);
CREATE INDEX idx_answers_difficulty ON interview_answers(difficulty);
CREATE INDEX idx_answers_is_skipped ON interview_answers(is_skipped);
CREATE INDEX idx_answers_score ON interview_answers(score);

-- RLS Policies
ALTER TABLE interview_answers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own answers"
    ON interview_answers FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM interview_sessions
            WHERE interview_sessions.id = interview_answers.session_id
            AND interview_sessions.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert own answers"
    ON interview_answers FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM interview_sessions
            WHERE interview_sessions.id = interview_answers.session_id
            AND interview_sessions.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete own answers"
    ON interview_answers FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM interview_sessions
            WHERE interview_sessions.id = interview_answers.session_id
            AND interview_sessions.user_id = auth.uid()
        )
    );

-- =====================================================
-- TABLE 5: interview_statistics (Aggregate stats)
-- Denormalized table for fast dashboard queries
-- =====================================================

CREATE TABLE IF NOT EXISTS interview_statistics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    total_interviews INTEGER DEFAULT 0,
    total_questions_answered INTEGER DEFAULT 0,
    average_overall_score NUMERIC(5,2),
    most_common_role TEXT,
    strongest_category TEXT,
    weakest_category TEXT,
    total_time_spent_seconds INTEGER DEFAULT 0,
    last_interview_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Index
CREATE INDEX idx_statistics_user_id ON interview_statistics(user_id);

-- RLS Policies
ALTER TABLE interview_statistics ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own statistics"
    ON interview_statistics FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own statistics"
    ON interview_statistics FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own statistics"
    ON interview_statistics FOR UPDATE
    USING (auth.uid() = user_id);

-- =====================================================
-- STORAGE BUCKETS (for Supabase Storage)
-- =====================================================

-- Create bucket for resumes (if not exists via Supabase dashboard)
-- INSERT INTO storage.buckets (id, name, public)
-- VALUES ('resumes', 'resumes', false);

-- RLS for storage (users can only access their own resumes)
-- CREATE POLICY "Users can upload own resumes"
--     ON storage.objects FOR INSERT
--     WITH CHECK (bucket_id = 'resumes' AND auth.uid()::text = (storage.foldername(name))[1]);

-- CREATE POLICY "Users can view own resumes"
--     ON storage.objects FOR SELECT
--     USING (bucket_id = 'resumes' AND auth.uid()::text = (storage.foldername(name))[1]);

-- CREATE POLICY "Users can delete own resumes"
--     ON storage.objects FOR DELETE
--     USING (bucket_id = 'resumes' AND auth.uid()::text = (storage.foldername(name))[1]);

-- =====================================================
-- HELPER FUNCTIONS
-- =====================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_resumes_updated_at
    BEFORE UPDATE ON resumes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_statistics_updated_at
    BEFORE UPDATE ON interview_statistics
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- VIEWS (for easier queries)
-- =====================================================

-- View: Recent interviews with resume details
CREATE OR REPLACE VIEW user_interview_history AS
SELECT 
    s.id,
    s.user_id,
    s.target_role,
    s.experience_level,
    s.interview_type,
    s.mode,
    s.total_questions,
    s.answered_questions,
    s.average_score,
    s.performance_tier,
    s.completed_at,
    s.duration_seconds,
    r.file_name as resume_name,
    COUNT(a.id) as total_answers
FROM interview_sessions s
LEFT JOIN resumes r ON s.resume_id = r.id
LEFT JOIN interview_answers a ON s.id = a.session_id
GROUP BY s.id, r.file_name;

-- =====================================================
-- COMMENTS (for documentation)
-- =====================================================

COMMENT ON TABLE resumes IS 'Stores uploaded resume files and parsed data';
COMMENT ON TABLE interview_sessions IS 'Stores completed interview sessions (not in-progress)';
COMMENT ON TABLE interview_answers IS 'Stores candidate answers for completed interviews';
COMMENT ON TABLE interview_statistics IS 'Denormalized aggregate statistics for dashboard';
COMMENT ON TABLE user_profiles IS 'Extended user profile information';

-- =====================================================
-- END OF MIGRATION
-- =====================================================
