import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";

export const DB_PATH =
  process.env.DEEP_THOUGHT_DB_PATH ??
  path.resolve(process.cwd(), "..", "logs", "deep_thought.db");

export type DashboardData = {
  dbPath: string;
  dbExists: boolean;
  generatedAt: string;
  stats: Stats;
  leaderboard: LeaderboardEntry[];
  candidates: Candidate[];
  evaluations: Evaluation[];
  history: HistoryEvent[];
  eliminations: Elimination[];
};

export type Stats = {
  candidates: number;
  evaluations: number;
  avgScore: number;
  topScore: number;
  byModel: Record<string, number>;
};

export type LeaderboardEntry = {
  rank: number;
  id: number;
  answer: string;
  sourceModel: string;
  sourceLabel: string;
  evaluations: number;
  avgScore: number;
  bestScore: number;
  lastEvaluatedAt: number | null;
};

export type Candidate = {
  id: number;
  answer: string;
  sourceModel: string;
  sourceLabel: string;
  parentAnswer: string | null;
  promptVariant: string | null;
  createdAt: number;
  evaluations: number;
  avgScore: number | null;
  bestScore: number | null;
};

export type Evaluation = {
  id: number;
  candidateId: number;
  answer: string;
  sourceModel: string;
  sourceLabel: string;
  evaluatorModel: string;
  opponentModel: string;
  rounds: number;
  scores: Record<string, number>;
  compositeScore: number;
  judgeReasoning: string | null;
  publicTranscript: TranscriptExcerpt[];
  createdAt: number;
};

export type TranscriptExcerpt = {
  role: "advocate" | "critic";
  round: number;
  text: string;
};

export type HistoryEvent = {
  id: number;
  phase: string;
  event: string;
  payload: unknown;
  createdAt: number;
};

export type Elimination = {
  rank: number;
  candidateId: number;
  answer: string;
  sourceModel: string;
  sourceLabel: string;
  avgScore: number;
  bestScore: number;
  evaluations: number;
  reason: string;
};

type Row = Record<string, unknown>;

export function getDashboardData(): DashboardData {
  if (!fs.existsSync(DB_PATH)) {
    return emptyDashboard(false);
  }

  try {
    const db = new Database(DB_PATH, { readonly: true, fileMustExist: true });
    db.pragma("query_only = ON");

    const stats = getStats(db);
    const leaderboard = getLeaderboard(db, 20);
    const candidates = getCandidates(db, 80);
    const evaluations = getEvaluations(db, 30);
    const history = getHistory(db, 60);
    const eliminations = getEliminations(db, 30);

    db.close();

    return {
      dbPath: DB_PATH,
      dbExists: true,
      generatedAt: new Date().toISOString(),
      stats,
      leaderboard,
      candidates,
      evaluations,
      history,
      eliminations
    };
  } catch (error) {
    return {
      ...emptyDashboard(true),
      history: [
        {
          id: 0,
          phase: "dashboard",
          event: "database_read_error",
          payload: error instanceof Error ? error.message : String(error),
          createdAt: Date.now() / 1000
        }
      ]
    };
  }
}

export function getCandidatesOnly(limit = 100): Candidate[] {
  if (!fs.existsSync(DB_PATH)) return [];
  const db = new Database(DB_PATH, { readonly: true, fileMustExist: true });
  db.pragma("query_only = ON");
  const rows = getCandidates(db, limit);
  db.close();
  return rows;
}

export function getEvaluationsOnly(limit = 50): Evaluation[] {
  if (!fs.existsSync(DB_PATH)) return [];
  const db = new Database(DB_PATH, { readonly: true, fileMustExist: true });
  db.pragma("query_only = ON");
  const rows = getEvaluations(db, limit);
  db.close();
  return rows;
}

export function getHistoryOnly(limit = 100): HistoryEvent[] {
  if (!fs.existsSync(DB_PATH)) return [];
  const db = new Database(DB_PATH, { readonly: true, fileMustExist: true });
  db.pragma("query_only = ON");
  const rows = getHistory(db, limit);
  db.close();
  return rows;
}

function emptyDashboard(dbExists: boolean): DashboardData {
  return {
    dbPath: DB_PATH,
    dbExists,
    generatedAt: new Date().toISOString(),
    stats: { candidates: 0, evaluations: 0, avgScore: 0, topScore: 0, byModel: {} },
    leaderboard: [],
    candidates: [],
    evaluations: [],
    history: [],
    eliminations: []
  };
}

function getStats(db: Database.Database): Stats {
  const row = db
    .prepare(
      `
      SELECT
        COUNT(DISTINCT q.id) AS candidates,
        COUNT(e.id) AS evaluations,
        COALESCE(AVG(e.composite_score), 0) AS avgScore,
        COALESCE(MAX(e.composite_score), 0) AS topScore
      FROM candidate_answers q
      LEFT JOIN candidate_evaluations e ON e.candidate_id = q.id
      `
    )
    .get() as Row;

  const byModelRows = db
    .prepare(
      `
      SELECT source_model AS sourceModel, COUNT(*) AS candidates
      FROM candidate_answers
      GROUP BY source_model
      ORDER BY source_model
      `
    )
    .all() as Row[];

  return {
    candidates: numberValue(row.candidates),
    evaluations: numberValue(row.evaluations),
    avgScore: numberValue(row.avgScore),
    topScore: numberValue(row.topScore),
    byModel: Object.fromEntries(
      byModelRows.map((modelRow) => [
        String(modelRow.sourceModel ?? "unknown"),
        numberValue(modelRow.candidates)
      ])
    )
  };
}

function getLeaderboard(db: Database.Database, limit: number): LeaderboardEntry[] {
  const rows = db
    .prepare(
      `
      SELECT
        q.id,
        q.answer,
        q.source_model AS sourceModel,
        COUNT(e.id) AS evaluations,
        COALESCE(AVG(e.composite_score), 0) AS avgScore,
        COALESCE(MAX(e.composite_score), 0) AS bestScore,
        MAX(e.created_at) AS lastEvaluatedAt
      FROM candidate_answers q
      JOIN candidate_evaluations e ON e.candidate_id = q.id
      GROUP BY q.id
      ORDER BY avgScore DESC, bestScore DESC, evaluations DESC
      LIMIT ?
      `
    )
    .all(limit) as Row[];

  return rows.map((row, index) => ({
    rank: index + 1,
    id: numberValue(row.id),
    answer: String(row.answer ?? ""),
    sourceModel: String(row.sourceModel ?? "unknown"),
    sourceLabel: modelLabel(String(row.sourceModel ?? "")),
    evaluations: numberValue(row.evaluations),
    avgScore: numberValue(row.avgScore),
    bestScore: numberValue(row.bestScore),
    lastEvaluatedAt: nullableNumber(row.lastEvaluatedAt)
  }));
}

function getCandidates(db: Database.Database, limit: number): Candidate[] {
  const rows = db
    .prepare(
      `
      SELECT
        q.id,
        q.answer,
        q.source_model AS sourceModel,
        q.parent_answer AS parentAnswer,
        q.prompt_variant AS promptVariant,
        q.created_at AS createdAt,
        COUNT(e.id) AS evaluations,
        AVG(e.composite_score) AS avgScore,
        MAX(e.composite_score) AS bestScore
      FROM candidate_answers q
      LEFT JOIN candidate_evaluations e ON e.candidate_id = q.id
      GROUP BY q.id
      ORDER BY q.created_at DESC
      LIMIT ?
      `
    )
    .all(limit) as Row[];

  return rows.map((row) => ({
    id: numberValue(row.id),
    answer: String(row.answer ?? ""),
    sourceModel: String(row.sourceModel ?? "unknown"),
    sourceLabel: modelLabel(String(row.sourceModel ?? "")),
    parentAnswer: nullableString(row.parentAnswer),
    promptVariant: nullableString(row.promptVariant),
    createdAt: numberValue(row.createdAt),
    evaluations: numberValue(row.evaluations),
    avgScore: nullableNumber(row.avgScore),
    bestScore: nullableNumber(row.bestScore)
  }));
}

function getEvaluations(db: Database.Database, limit: number): Evaluation[] {
  const rows = db
    .prepare(
      `
      SELECT
        e.id,
        e.candidate_id AS candidateId,
        q.answer,
        q.source_model AS sourceModel,
        e.evaluator_model AS evaluatorModel,
        e.opponent_model AS opponentModel,
        e.rounds,
        e.transcript_json AS transcriptJson,
        e.scores_json AS scoresJson,
        e.composite_score AS compositeScore,
        e.judge_reasoning AS judgeReasoning,
        e.created_at AS createdAt
      FROM candidate_evaluations e
      JOIN candidate_answers q ON q.id = e.candidate_id
      ORDER BY e.created_at DESC
      LIMIT ?
      `
    )
    .all(limit) as Row[];

  return rows.map((row) => ({
    id: numberValue(row.id),
    candidateId: numberValue(row.candidateId),
    answer: String(row.answer ?? ""),
    sourceModel: String(row.sourceModel ?? "unknown"),
    sourceLabel: modelLabel(String(row.sourceModel ?? "")),
    evaluatorModel: String(row.evaluatorModel ?? "unknown"),
    opponentModel: String(row.opponentModel ?? "unknown"),
    rounds: numberValue(row.rounds),
    scores: parseScoreMap(String(row.scoresJson ?? "{}")),
    compositeScore: numberValue(row.compositeScore),
    judgeReasoning: nullableString(row.judgeReasoning),
    publicTranscript: transcriptExcerpts(String(row.transcriptJson ?? "{}")),
    createdAt: numberValue(row.createdAt)
  }));
}

function getHistory(db: Database.Database, limit: number): HistoryEvent[] {
  const rows = db
    .prepare(
      `
      SELECT id, phase, event, payload_json AS payloadJson, created_at AS createdAt
      FROM phase_log
      ORDER BY created_at DESC
      LIMIT ?
      `
    )
    .all(limit) as Row[];

  return rows.map((row) => ({
    id: numberValue(row.id),
    phase: String(row.phase ?? "unknown"),
    event: String(row.event ?? "event"),
    payload: parseUnknown(String(row.payloadJson ?? "null")),
    createdAt: numberValue(row.createdAt)
  }));
}

function getEliminations(db: Database.Database, limit: number): Elimination[] {
  const rows = db
    .prepare(
      `
      WITH ranked AS (
        SELECT
          q.id,
          q.answer,
          q.source_model AS sourceModel,
          COUNT(e.id) AS evaluations,
          AVG(e.composite_score) AS avgScore,
          MAX(e.composite_score) AS bestScore,
          RANK() OVER (ORDER BY AVG(e.composite_score) DESC, MAX(e.composite_score) DESC) AS rank
        FROM candidate_answers q
        JOIN candidate_evaluations e ON e.candidate_id = q.id
        GROUP BY q.id
      )
      SELECT *
      FROM ranked
      WHERE rank > 10
      ORDER BY avgScore ASC, bestScore ASC
      LIMIT ?
      `
    )
    .all(limit) as Row[];

  return rows.map((row) => ({
    rank: numberValue(row.rank),
    candidateId: numberValue(row.id),
    answer: String(row.answer ?? ""),
    sourceModel: String(row.sourceModel ?? "unknown"),
    sourceLabel: modelLabel(String(row.sourceModel ?? "")),
    avgScore: numberValue(row.avgScore),
    bestScore: numberValue(row.bestScore),
    evaluations: numberValue(row.evaluations),
    reason: "Outside current top 10 by average evaluation score"
  }));
}

function transcriptExcerpts(rawJson: string): TranscriptExcerpt[] {
  const parsed = parseUnknown(rawJson);
  if (!isRecord(parsed)) return [];

  const advocate = Array.isArray(parsed.advocate) ? parsed.advocate : [];
  const critic = Array.isArray(parsed.critic) ? parsed.critic : [];
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

function parseScoreMap(rawJson: string): Record<string, number> {
  const parsed = parseUnknown(rawJson);
  if (!isRecord(parsed)) return {};

  return Object.fromEntries(
    Object.entries(parsed)
      .filter(([, value]) => typeof value === "number")
      .map(([key, value]) => [key, value as number])
  );
}

function parseUnknown(rawJson: string): unknown {
  try {
    return JSON.parse(rawJson);
  } catch {
    return null;
  }
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

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
