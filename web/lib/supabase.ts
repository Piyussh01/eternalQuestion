import type {
  Candidate,
  DashboardData,
  Elimination,
  Evaluation,
  HistoryEvent,
  LeaderboardEntry,
  Stats,
  TranscriptExcerpt
} from "@/lib/db";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL?.replace(/\/$/, "");
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

type Row = Record<string, unknown>;

export function hasSupabaseConfig() {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}

export async function getSupabaseDashboardData(): Promise<DashboardData> {
  const [candidatesRaw, evaluationsRaw, historyRaw] = await Promise.all([
    supabaseGet("public_candidates?select=*&order=created_at.desc&limit=500"),
    supabaseGet("public_evaluations?select=*&order=created_at.desc&limit=300"),
    supabaseGet("public_phase_log?select=*&order=created_at.desc&limit=300")
  ]);

  const candidates = mapCandidates(candidatesRaw);
  const evaluations = mapEvaluations(evaluationsRaw, candidates);
  const history = mapHistory(historyRaw);
  const stats = getStats(candidates, evaluations);
  const leaderboard = getLeaderboard(candidates, evaluations, 20);
  const eliminations = getEliminations(candidates, evaluations, 30);

  return {
    dbPath: "supabase",
    dbExists: true,
    generatedAt: new Date().toISOString(),
    stats,
    leaderboard,
    candidates: candidates.slice(0, 80),
    evaluations: evaluations.slice(0, 30),
    history: history.slice(0, 60),
    eliminations
  };
}

export async function getSupabaseCandidatesOnly(limit = 100): Promise<Candidate[]> {
  return mapCandidates(
    await supabaseGet(`public_candidates?select=*&order=created_at.desc&limit=${limit}`)
  );
}

export async function getSupabaseEvaluationsOnly(limit = 50): Promise<Evaluation[]> {
  const [candidatesRaw, evaluationsRaw] = await Promise.all([
    supabaseGet("public_candidates?select=*&limit=1000"),
    supabaseGet(`public_evaluations?select=*&order=created_at.desc&limit=${limit}`)
  ]);
  return mapEvaluations(evaluationsRaw, mapCandidates(candidatesRaw));
}

export async function getSupabaseHistoryOnly(limit = 100): Promise<HistoryEvent[]> {
  return mapHistory(await supabaseGet(`public_phase_log?select=*&order=created_at.desc&limit=${limit}`));
}

async function supabaseGet(path: string): Promise<Row[]> {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return [];
  const response = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    cache: "no-store",
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`
    }
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Supabase returned ${response.status}: ${body}`);
  }

  return (await response.json()) as Row[];
}

function mapCandidates(rows: Row[]): Candidate[] {
  return rows.map((row) => ({
    id: numberValue(row.id),
    answer: String(row.answer ?? ""),
    sourceModel: String(row.source_model ?? "unknown"),
    sourceLabel: modelLabel(String(row.source_model ?? "")),
    parentAnswer: nullableString(row.parent_answer),
    promptVariant: nullableString(row.prompt_variant),
    createdAt: numberValue(row.created_at),
    evaluations: 0,
    avgScore: null,
    bestScore: null
  }));
}

function mapEvaluations(rows: Row[], candidates: Candidate[]): Evaluation[] {
  const byId = new Map(candidates.map((candidate) => [candidate.id, candidate]));
  return rows.map((row) => {
    const candidate = byId.get(numberValue(row.candidate_id));
    const sourceModel = candidate?.sourceModel ?? "unknown";
    return {
      id: numberValue(row.id),
      candidateId: numberValue(row.candidate_id),
      answer: candidate?.answer ?? "",
      sourceModel,
      sourceLabel: modelLabel(sourceModel),
      evaluatorModel: String(row.evaluator_model ?? "unknown"),
      opponentModel: String(row.opponent_model ?? "unknown"),
      rounds: numberValue(row.rounds),
      scores: scoreMap(row.scores_json),
      compositeScore: numberValue(row.composite_score),
      judgeReasoning: nullableString(row.judge_reasoning),
      publicTranscript: transcriptExcerpts(row.transcript_json),
      createdAt: numberValue(row.created_at)
    };
  });
}

function mapHistory(rows: Row[]): HistoryEvent[] {
  return rows.map((row) => ({
    id: numberValue(row.id),
    phase: String(row.phase ?? "unknown"),
    event: String(row.event ?? "event"),
    payload: row.payload_json ?? null,
    createdAt: numberValue(row.created_at)
  }));
}

function getStats(candidates: Candidate[], evaluations: Evaluation[]): Stats {
  const byModel: Record<string, number> = {};
  for (const candidate of candidates) {
    byModel[candidate.sourceModel] = (byModel[candidate.sourceModel] ?? 0) + 1;
  }
  return {
    candidates: candidates.length,
    evaluations: evaluations.length,
    avgScore: average(evaluations.map((evaluation) => evaluation.compositeScore)),
    topScore: Math.max(0, ...evaluations.map((evaluation) => evaluation.compositeScore)),
    byModel
  };
}

function getLeaderboard(
  candidates: Candidate[],
  evaluations: Evaluation[],
  limit: number
): LeaderboardEntry[] {
  const grouped = groupEvaluations(evaluations);
  return candidates
    .map((candidate) => {
      const candidateEvaluations = grouped.get(candidate.id) ?? [];
      return {
        candidate,
        evaluations: candidateEvaluations.length,
        avgScore: average(candidateEvaluations.map((evaluation) => evaluation.compositeScore)),
        bestScore: Math.max(0, ...candidateEvaluations.map((evaluation) => evaluation.compositeScore)),
        lastEvaluatedAt: Math.max(0, ...candidateEvaluations.map((evaluation) => evaluation.createdAt)) || null
      };
    })
    .filter((entry) => entry.evaluations > 0)
    .sort((a, b) => b.avgScore - a.avgScore || b.bestScore - a.bestScore || b.evaluations - a.evaluations)
    .slice(0, limit)
    .map((entry, index) => ({
      rank: index + 1,
      id: entry.candidate.id,
      answer: entry.candidate.answer,
      sourceModel: entry.candidate.sourceModel,
      sourceLabel: entry.candidate.sourceLabel,
      evaluations: entry.evaluations,
      avgScore: entry.avgScore,
      bestScore: entry.bestScore,
      lastEvaluatedAt: entry.lastEvaluatedAt
    }));
}

function getEliminations(
  candidates: Candidate[],
  evaluations: Evaluation[],
  limit: number
): Elimination[] {
  const leaderboard = getLeaderboard(candidates, evaluations, candidates.length);
  return leaderboard
    .slice(10)
    .reverse()
    .slice(0, limit)
    .map((entry) => ({
      rank: entry.rank,
      candidateId: entry.id,
      answer: entry.answer,
      sourceModel: entry.sourceModel,
      sourceLabel: entry.sourceLabel,
      avgScore: entry.avgScore,
      bestScore: entry.bestScore,
      evaluations: entry.evaluations,
      reason: "Outside current top 10 by average evaluation score"
    }));
}

function groupEvaluations(evaluations: Evaluation[]) {
  const grouped = new Map<number, Evaluation[]>();
  for (const evaluation of evaluations) {
    grouped.set(evaluation.candidateId, [...(grouped.get(evaluation.candidateId) ?? []), evaluation]);
  }
  return grouped;
}

function transcriptExcerpts(value: unknown): TranscriptExcerpt[] {
  if (!isRecord(value)) return [];
  const advocate = Array.isArray(value.advocate) ? value.advocate : [];
  const critic = Array.isArray(value.critic) ? value.critic : [];
  const excerpts: TranscriptExcerpt[] = [];
  const rounds = Math.max(advocate.length, critic.length);

  for (let index = 0; index < rounds; index += 1) {
    if (typeof advocate[index] === "string") {
      excerpts.push({ role: "advocate", round: index + 1, text: trimExcerpt(advocate[index]) });
    }
    if (typeof critic[index] === "string") {
      excerpts.push({ role: "critic", round: index + 1, text: trimExcerpt(critic[index]) });
    }
  }

  return excerpts;
}

function scoreMap(value: unknown): Record<string, number> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value).filter(([, score]) => typeof score === "number")
  ) as Record<string, number>;
}

function average(values: number[]): number {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function modelLabel(model: string): string {
  const lower = model.toLowerCase();
  if (lower.includes("moe") || lower.includes("explorer")) return "Explorer / MoE";
  if (lower.includes("dense") || lower.includes("reasoner")) return "Reasoner / Dense";
  return model || "Unknown model";
}

function trimExcerpt(text: string): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > 420 ? `${normalized.slice(0, 420)}...` : normalized;
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
