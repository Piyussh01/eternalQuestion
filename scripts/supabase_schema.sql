-- Public read model for the 24-hour meaning-of-life experiment.
-- Run this once in the Supabase SQL editor for project mwcsgnatylzgkxjvjihb.

CREATE TABLE IF NOT EXISTS public.public_candidates (
  id BIGINT PRIMARY KEY,
  answer TEXT NOT NULL,
  source_model TEXT NOT NULL,
  parent_answer TEXT,
  prompt_variant TEXT,
  created_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS public.public_evaluations (
  id BIGINT PRIMARY KEY,
  candidate_id BIGINT NOT NULL REFERENCES public.public_candidates(id) ON DELETE CASCADE,
  evaluator_model TEXT NOT NULL,
  opponent_model TEXT NOT NULL,
  rounds INTEGER NOT NULL,
  transcript_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  scores_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  composite_score DOUBLE PRECISION NOT NULL,
  judge_reasoning TEXT,
  config_json JSONB,
  created_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS public.public_phase_log (
  id BIGINT PRIMARY KEY,
  phase TEXT NOT NULL,
  event TEXT NOT NULL,
  payload_json JSONB,
  created_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS public_candidates_source_idx
  ON public.public_candidates(source_model);

CREATE INDEX IF NOT EXISTS public_evaluations_score_idx
  ON public.public_evaluations(composite_score DESC);

CREATE INDEX IF NOT EXISTS public_evaluations_created_idx
  ON public.public_evaluations(created_at DESC);

CREATE INDEX IF NOT EXISTS public_phase_log_created_idx
  ON public.public_phase_log(created_at DESC);

ALTER TABLE public.public_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.public_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.public_phase_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public candidates are readable" ON public.public_candidates;
CREATE POLICY "public candidates are readable"
  ON public.public_candidates FOR SELECT
  USING (true);

DROP POLICY IF EXISTS "public evaluations are readable" ON public.public_evaluations;
CREATE POLICY "public evaluations are readable"
  ON public.public_evaluations FOR SELECT
  USING (true);

DROP POLICY IF EXISTS "public phase log is readable" ON public.public_phase_log;
CREATE POLICY "public phase log is readable"
  ON public.public_phase_log FOR SELECT
  USING (true);
