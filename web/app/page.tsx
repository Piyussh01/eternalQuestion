"use client";

import {
  Activity,
  BadgeCheck,
  BrainCircuit,
  ChevronDown,
  Clock3,
  Database,
  Gauge,
  History,
  Medal,
  RefreshCcw,
  Scale,
  Search,
  ShieldX,
  Sparkles,
  Swords
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { DashboardData, Evaluation, LeaderboardEntry } from "@/lib/db";

const POLL_MS = 5000;

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [selectedEvaluationId, setSelectedEvaluationId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      try {
        const response = await fetch("/api/dashboard", { cache: "no-store" });
        if (!response.ok) throw new Error(`Dashboard API returned ${response.status}`);
        const payload = (await response.json()) as DashboardData;
        if (!mounted) return;
        setData(payload);
        setSelectedEvaluationId((current) => current ?? payload.evaluations[0]?.id ?? null);
        setError(null);
      } catch (loadError) {
        if (!mounted) return;
        setError(loadError instanceof Error ? loadError.message : String(loadError));
      } finally {
        if (mounted) setIsLoading(false);
      }
    }

    load();
    const interval = window.setInterval(load, POLL_MS);

    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const filteredCandidates = useMemo(() => {
    if (!data) return [];
    const normalized = query.trim().toLowerCase();
    if (!normalized) return data.candidates;

    return data.candidates.filter(
      (candidate) =>
        candidate.answer.toLowerCase().includes(normalized) ||
        candidate.sourceModel.toLowerCase().includes(normalized) ||
        candidate.sourceLabel.toLowerCase().includes(normalized)
    );
  }, [data, query]);

  const selectedEvaluation =
    data?.evaluations.find((evaluation) => evaluation.id === selectedEvaluationId) ??
    data?.evaluations[0] ??
    null;

  return (
    <main>
      <header className="topbar">
        <div>
          <p className="eyebrow">Deep Thought 2.0</p>
          <h1>Public Reasoning Trace</h1>
        </div>
        <div className="statusCluster">
          <div className={data?.dbExists ? "status ok" : "status missing"}>
            <Database size={16} />
            <span>{data?.dbExists ? "DB connected" : "Waiting for DB"}</span>
          </div>
          <div className="status">
            <RefreshCcw size={16} />
            <span>{isLoading ? "Loading" : `Polling ${POLL_MS / 1000}s`}</span>
          </div>
        </div>
      </header>

      {error ? <div className="banner error">{error}</div> : null}
      {data && !data.dbExists ? (
        <div className="banner">
          No experiment database found at <code>{data.dbPath}</code>. Start the experiment and this
          dashboard will populate automatically.
        </div>
      ) : null}

      <section className="metrics">
        <Metric icon={<Sparkles size={18} />} label="Candidates" value={data?.stats.candidates ?? 0} />
        <Metric icon={<Swords size={18} />} label="Evaluations" value={data?.stats.evaluations ?? 0} />
        <Metric
          icon={<Gauge size={18} />}
          label="Average score"
          value={formatScore(data?.stats.avgScore ?? 0)}
        />
        <Metric
          icon={<Medal size={18} />}
          label="Top score"
          value={formatScore(data?.stats.topScore ?? 0)}
        />
      </section>

      <section className="grid">
        <Panel className="leaderboard" title="Leaderboard" icon={<Medal size={18} />}>
          {data?.leaderboard.length ? (
            <div className="rankList">
              {data.leaderboard.map((entry) => (
                <LeaderboardRow key={entry.id} entry={entry} />
              ))}
            </div>
          ) : (
            <EmptyState text="No evaluated candidates yet." />
          )}
        </Panel>

        <Panel title="Model Sources" icon={<BrainCircuit size={18} />}>
          <div className="sourceGrid">
            {Object.entries(data?.stats.byModel ?? {}).map(([model, count]) => (
              <div className="sourceBox" key={model}>
                <span>{sourceLabel(model)}</span>
                <strong>{count}</strong>
                <small>{model}</small>
              </div>
            ))}
            {!Object.keys(data?.stats.byModel ?? {}).length ? <EmptyState text="No sources yet." /> : null}
          </div>
        </Panel>

        <Panel className="tracePanel" title="Latest Public Transcript" icon={<Scale size={18} />}>
          <EvaluationPicker
            evaluations={data?.evaluations ?? []}
            selectedEvaluationId={selectedEvaluation?.id ?? null}
            onSelect={setSelectedEvaluationId}
          />
          {selectedEvaluation ? <EvaluationTrace evaluation={selectedEvaluation} /> : <EmptyState text="No transcript excerpts yet." />}
        </Panel>

        <Panel title="Candidates" icon={<Search size={18} />}>
          <label className="searchBox">
            <Search size={16} />
            <input
              aria-label="Filter candidates"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter candidates or source"
            />
          </label>
          <div className="candidateList">
            {filteredCandidates.map((candidate) => (
              <article className="candidate" key={candidate.id}>
                <div>
                  <strong>{candidate.answer}</strong>
                  <span>{candidate.sourceLabel}</span>
                </div>
                <div className="scorePill">{candidate.avgScore === null ? "new" : formatScore(candidate.avgScore)}</div>
              </article>
            ))}
            {!filteredCandidates.length ? <EmptyState text="No matching candidates." /> : null}
          </div>
        </Panel>

        <Panel title="Elimination Watch" icon={<ShieldX size={18} />}>
          <div className="historyList">
            {data?.eliminations.map((item) => (
              <article className="historyItem" key={item.candidateId}>
                <div>
                  <strong>Rank {item.rank}</strong>
                  <p>{item.answer}</p>
                  <small>{item.reason}</small>
                </div>
                <span>{formatScore(item.avgScore)}</span>
              </article>
            ))}
            {!data?.eliminations.length ? <EmptyState text="No candidates have fallen outside the top 10 yet." /> : null}
          </div>
        </Panel>

        <Panel title="Phase History" icon={<History size={18} />}>
          <div className="historyList">
            {data?.history.map((event) => (
              <article className="historyItem" key={event.id}>
                <div>
                  <strong>{event.event}</strong>
                  <p>{event.phase}</p>
                  <small>{formatTime(event.createdAt)}</small>
                </div>
                <ChevronDown size={16} />
              </article>
            ))}
            {!data?.history.length ? <EmptyState text="No phase events recorded yet." /> : null}
          </div>
        </Panel>
      </section>

      <footer>
        <Clock3 size={16} />
        <span>Last refresh {data ? formatGeneratedAt(data.generatedAt) : "pending"}</span>
      </footer>
    </main>
  );
}

function Metric({
  icon,
  label,
  value
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
}) {
  return (
    <article className="metric">
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function Panel({
  title,
  icon,
  children,
  className = ""
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panelTitle">
        {icon}
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function LeaderboardRow({ entry }: { entry: LeaderboardEntry }) {
  return (
    <article className="rankRow">
      <div className="rankBadge">{entry.rank}</div>
      <div className="rankBody">
        <strong>{entry.answer}</strong>
        <span>
          {entry.sourceLabel} · {entry.evaluations} evals · best {formatScore(entry.bestScore)}
        </span>
      </div>
      <div className="rankScore">{formatScore(entry.avgScore)}</div>
    </article>
  );
}

function EvaluationPicker({
  evaluations,
  selectedEvaluationId,
  onSelect
}: {
  evaluations: Evaluation[];
  selectedEvaluationId: number | null;
  onSelect: (id: number) => void;
}) {
  if (!evaluations.length) return null;

  return (
    <select
      className="traceSelect"
      value={selectedEvaluationId ?? evaluations[0].id}
      onChange={(event) => onSelect(Number(event.target.value))}
      aria-label="Select evaluation trace"
    >
      {evaluations.map((evaluation) => (
        <option key={evaluation.id} value={evaluation.id}>
          #{evaluation.id} · {formatScore(evaluation.compositeScore)} · {evaluation.answer.slice(0, 72)}
        </option>
      ))}
    </select>
  );
}

function EvaluationTrace({ evaluation }: { evaluation: Evaluation }) {
  return (
    <div className="trace">
      <div className="traceHeader">
        <div>
          <p className="eyebrow">Candidate answer</p>
          <h3>{evaluation.answer}</h3>
          <span>
            Advocate {evaluation.evaluatorModel} · Critic {evaluation.opponentModel} · {evaluation.rounds} rounds
          </span>
        </div>
        <div className="traceScore">{formatScore(evaluation.compositeScore)}</div>
      </div>

      <div className="scoreGrid">
        {Object.entries(evaluation.scores).map(([key, value]) => (
          <div key={key}>
            <span>{key}</span>
            <strong>{formatScore(value)}</strong>
          </div>
        ))}
      </div>

      <div className="transcript">
        {evaluation.publicTranscript.map((excerpt, index) => (
          <article className={excerpt.role} key={`${excerpt.role}-${excerpt.round}-${index}`}>
            <BadgeCheck size={16} />
            <div>
              <strong>
                {excerpt.role} · round {excerpt.round}
              </strong>
              <p>{excerpt.text}</p>
            </div>
          </article>
        ))}
      </div>

      <div className="judge">
        <div>
          <Activity size={16} />
          <strong>Judge public reasoning</strong>
        </div>
        <p>{evaluation.judgeReasoning || "No judge reasoning recorded."}</p>
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="empty">{text}</p>;
}

function formatScore(value: number) {
  return value.toFixed(2);
}

function formatTime(seconds: number) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(seconds * 1000));
}

function formatGeneratedAt(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(value));
}

function sourceLabel(model: string) {
  const lower = model.toLowerCase();
  if (lower.includes("moe") || lower.includes("explorer")) return "Explorer / MoE";
  if (lower.includes("dense") || lower.includes("reasoner")) return "Reasoner / Dense";
  return model;
}
