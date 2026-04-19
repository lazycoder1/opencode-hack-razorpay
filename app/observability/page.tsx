"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type RunStep = {
  name: string;
  status: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  metadata: Record<string, unknown>;
};

type GenerationRun = {
  id: string;
  company_name: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  total_duration_ms: number | null;
  model_name: string | null;
  prompt_preview: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  llm_duration_ms: number | null;
  microsite_slug: string | null;
  langsmith_project: string | null;
  langsmith_trace_id: string | null;
  langsmith_run_id: string | null;
  langsmith_trace_url: string | null;
  error: string | null;
  steps: RunStep[];
};

type ApiRequestEvent = {
  id: string;
  path: string;
  method: string;
  status_code: number;
  duration_ms: number;
  occurred_at: string;
};

type LangSmithRunSummary = {
  id: string;
  name: string | null;
  run_type: string | null;
  status: string | null;
  start_time: string | null;
  end_time: string | null;
  trace_id: string | null;
  url: string | null;
  error_message: string | null;
  failed_steps: LangSmithFailureSummary[];
};

type LangSmithFailureSummary = {
  id: string;
  name: string | null;
  run_type: string | null;
  error_message: string;
  parent_run_id: string | null;
};

type LangSmithStatus = {
  enabled: boolean;
  project_name: string | null;
  api_url: string | null;
  project_url: string | null;
  recent_runs: LangSmithRunSummary[];
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function ObservabilityPage() {
  const [runs, setRuns] = useState<GenerationRun[]>([]);
  const [requests, setRequests] = useState<ApiRequestEvent[]>([]);
  const [langsmith, setLangsmith] = useState<LangSmithStatus | null>(null);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "completed" | "failed">("all");
  const [compareMode, setCompareMode] = useState(false);
  const [compareIds, setCompareIds] = useState<string[]>([]);

  useEffect(() => {
    async function loadObservability() {
      setLoading(true);

      try {
        const [runsResponse, requestsResponse, langsmithResponse, councilResponse] = await Promise.all([
          fetch(`${apiBaseUrl}/api/observability/runs`),
          fetch(`${apiBaseUrl}/api/observability/requests`),
          fetch(`${apiBaseUrl}/api/observability/langsmith`),
          fetch(`${apiBaseUrl}/api/council/runs`),
        ]);

        if (!runsResponse.ok) {
          throw new Error(`Unable to load runs: ${runsResponse.status}`);
        }

        if (!requestsResponse.ok) {
          throw new Error(`Unable to load requests: ${requestsResponse.status}`);
        }

        const runsData: GenerationRun[] = await runsResponse.json();
        const requestsData: ApiRequestEvent[] = await requestsResponse.json();
        const langsmithData: LangSmithStatus = langsmithResponse.ok ? await langsmithResponse.json() : { enabled: false, project_name: null, api_url: null, project_url: null, recent_runs: [] };

        // Merge council runs into the same format
        const councilRuns: GenerationRun[] = [];
        if (councilResponse.ok) {
          const councilData: Array<Record<string, unknown>> = await councilResponse.json();
          for (const cr of councilData) {
            const steps = (cr.steps as Array<Record<string, unknown>> ?? []).map((s) => ({
              name: (s.step_name as string) ?? "",
              status: (s.status as string) ?? "",
              started_at: (s.started_at as string) ?? "",
              ended_at: (s.started_at as string) ?? "",
              duration_ms: (s.duration_ms as number) ?? 0,
              metadata: {
                agent_role: s.agent_role,
                model_name: s.model_name,
                input_tokens: s.input_tokens,
                output_tokens: s.output_tokens,
                cost_usd: s.cost_usd,
                ...(s.metadata as Record<string, unknown> ?? {}),
              },
            }));
            const totalTokens = steps.reduce((sum, s) => sum + ((s.metadata.input_tokens as number) ?? 0) + ((s.metadata.output_tokens as number) ?? 0), 0);
            councilRuns.push({
              id: cr.run_id as string,
              company_name: `${cr.source_company} x ${cr.prospect}`,
              status: cr.status as string,
              started_at: cr.started_at as string,
              completed_at: (cr.completed_at as string) ?? null,
              total_duration_ms: (cr.total_duration_ms as number) ?? null,
              model_name: steps.find((s) => s.metadata.model_name)?.metadata.model_name as string ?? null,
              prompt_preview: null,
              input_tokens: null,
              output_tokens: null,
              total_tokens: totalTokens || null,
              llm_duration_ms: (cr.total_duration_ms as number) ?? null,
              microsite_slug: null,
              langsmith_project: null,
              langsmith_trace_id: null,
              langsmith_run_id: null,
              langsmith_trace_url: null,
              error: null,
              steps,
            });
          }
        }

        // Merge and deduplicate by id, council runs first (newer)
        const seenIds = new Set<string>();
        const merged: GenerationRun[] = [];
        for (const run of [...councilRuns, ...runsData]) {
          if (!seenIds.has(run.id)) {
            seenIds.add(run.id);
            merged.push(run);
          }
        }

        setRuns(merged);
        setRequests(requestsData);
        setLangsmith(langsmithData);
        setSelectedRunId(merged[0]?.id ?? "");
      } catch (caughtError) {
        setError(caughtError instanceof Error ? caughtError.message : "Unable to load observability data");
      } finally {
        setLoading(false);
      }
    }

    void loadObservability();
  }, []);

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? runs[0] ?? null,
    [runs, selectedRunId],
  );

  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      const matchesSearch = !searchQuery || run.company_name.toLowerCase().includes(searchQuery.toLowerCase()) || run.id.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStatus = statusFilter === "all" || (statusFilter === "completed" ? run.status === "completed" : run.status !== "completed");
      return matchesSearch && matchesStatus;
    });
  }, [runs, searchQuery, statusFilter]);

  const compareRuns = useMemo(
    () => compareIds.map((id) => runs.find((r) => r.id === id)).filter(Boolean) as GenerationRun[],
    [runs, compareIds],
  );

  const regressionRuns = useMemo(() => runs.filter((r) => r.status !== "completed" || r.error), [runs]);

  const completedRuns = runs.filter((run) => run.status === "completed").length;
  const failedRuns = runs.filter((run) => run.status !== "completed").length;
  const averageLatency =
    requests.length === 0
      ? null
      : requests.reduce((total, request) => total + request.duration_ms, 0) / requests.length;

  return (
    <main className="pageShell">
      <nav className="topbar">
        <div className="brand">
          <div className="brandIcon">OB</div>
          <div className="brandBlock">
            <strong className="brandTitle">Observability</strong>
            <span className="brandCaption">Runs, timings, prompts, and request latency</span>
          </div>
        </div>

        <div className="navCluster">
          <Link className="navLink" href="/">
            New batch
          </Link>
          {selectedRun?.microsite_slug ? (
            <Link className="navLink" href={`/microsites/${selectedRun.microsite_slug}`}>
              Open output
            </Link>
          ) : null}
        </div>
      </nav>

      <section className="pageIntro">
        <div>
          <p className="kicker">Operator view</p>
          <h1 className="pageTitle">Inspect generation quality without leaving the product.</h1>
          <p className="sectionText">The trace surface stays compact, list-detail, and useful for a mentor or operator who wants timing, prompt, and request evidence quickly.</p>
        </div>

        <div className="metricGrid metricGridThree compactMetrics">
          <article className="metricCard">
            <span>Completed runs</span>
            <strong>{completedRuns}</strong>
          </article>
          <article className="metricCard">
            <span>Failed runs</span>
            <strong>{failedRuns}</strong>
          </article>
          <article className="metricCard">
            <span>Avg latency</span>
            <strong>{averageLatency?.toFixed(1) ?? "-"} ms</strong>
          </article>
          <article className="metricCard">
            <span>LangSmith</span>
            <strong>{langsmith?.enabled ? "Connected" : "Off"}</strong>
          </article>
        </div>
      </section>

      {regressionRuns.length > 0 && !loading ? (
        <div className="alertBanner alertError">
          <strong>Regression Alert</strong>
          <span>{regressionRuns.length} run{regressionRuns.length !== 1 ? "s" : ""} failed or errored — quality may have degraded. Investigate below.</span>
        </div>
      ) : null}

      {error ? <p className="errorText">{error}</p> : null}

      {loading ? (
        <section className="panel pageLoading">
          <div className="pageSpinner" />
          <div>
            <p className="kicker">Observability loading</p>
            <h2 className="sectionTitle">Collecting traces, request logs, and LangSmith status.</h2>
          </div>
        </section>
      ) : null}

      <section className="opsGrid">
        <aside className="panel selectorPanel">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Runs</p>
              <h2 className="sectionTitle">Generation history</h2>
            </div>
            <button className={`buttonSecondary ${compareMode ? "activeToggle" : ""}`} type="button" onClick={() => { setCompareMode(!compareMode); setCompareIds([]); }}>
              {compareMode ? "Exit diff" : "Run diff"}
            </button>
          </div>
          <div className="searchFilterBar">
            <input className="searchInput" type="text" placeholder="Search runs..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
            <select className="filterSelect" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as "all" | "completed" | "failed")}>
              <option value="all">All status</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </div>
          {compareMode ? <p className="compareHint">Select two runs to compare</p> : null}

          {loading ? (
            <div className="emptyPanel">
              <p>Loading run history...</p>
            </div>
          ) : filteredRuns.length === 0 ? (
            <div className="emptyPanel">
              <p>{runs.length === 0 ? "No runs captured yet." : "No runs match your filters."}</p>
            </div>
          ) : (
            <div className="selectorList">
              {filteredRuns.map((run) => (
                <button
                  key={run.id}
                  className={`selectorButton ${compareMode ? (compareIds.includes(run.id) ? "active" : "") : (run.id === selectedRun?.id ? "active" : "")}`}
                  onClick={() => {
                    if (compareMode) {
                      setCompareIds((prev) => prev.includes(run.id) ? prev.filter((x) => x !== run.id) : prev.length < 2 ? [...prev, run.id] : [prev[1], run.id]);
                    } else {
                      setSelectedRunId(run.id);
                    }
                  }}
                  type="button"
                >
                  <div className="selectorTop">
                    <span>{run.status}</span>
                    <strong>{run.total_duration_ms?.toFixed(0) ?? "-"} ms</strong>
                  </div>
                  <strong className="selectorTitle">{run.company_name}</strong>
                  <p>{new Date(run.started_at).toLocaleString()}</p>
                  {compareMode && compareIds.includes(run.id) ? <span className="compareBadge">#{compareIds.indexOf(run.id) + 1}</span> : null}
                </button>
              ))}
            </div>
          )}
        </aside>

        {compareMode && compareRuns.length === 2 ? (
          <section className="detailStack">
            <article className="panel detailPanel">
              <div className="previewHeader">
                <div>
                  <p className="kicker">Run diff</p>
                  <h2 className="sectionTitle">Comparing two runs</h2>
                </div>
              </div>
              <div className="diffGrid">
                {compareRuns.map((run, i) => (
                  <div className="diffColumn" key={run.id}>
                    <p className="kicker">Run #{i + 1}</p>
                    <strong className="selectorTitle">{run.company_name}</strong>
                    <span className={`statusChip ${run.status === "completed" ? "statusReady" : "statusError"}`}>{run.status}</span>
                    <div className="metricGrid compactMetrics" style={{ marginTop: 8 }}>
                      <article className="metricCard"><span>Duration</span><strong>{run.total_duration_ms?.toFixed(0) ?? "-"} ms</strong></article>
                      <article className="metricCard"><span>Tokens</span><strong>{run.total_tokens ?? "-"}</strong></article>
                      <article className="metricCard"><span>Model</span><strong>{run.model_name ?? "-"}</strong></article>
                    </div>
                    <div className="stepList" style={{ marginTop: 8 }}>
                      {run.steps.map((step) => (
                        <article className="stepItem" key={`${step.name}-${step.started_at}`}>
                          <div className="stepHead"><strong>{step.name}</strong><span>{step.duration_ms.toFixed(0)} ms</span></div>
                          <p className="stepStatus">{step.status}</p>
                        </article>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              {(() => {
                const [a, b] = compareRuns;
                const dDur = (a.total_duration_ms ?? 0) - (b.total_duration_ms ?? 0);
                const dTok = (a.total_tokens ?? 0) - (b.total_tokens ?? 0);
                return (
                  <div className="diffSummary">
                    <p className="kicker">Delta (Run #1 vs #2)</p>
                    <div className="metricGrid metricGridThree compactMetrics">
                      <article className="metricCard"><span>Duration</span><strong className={dDur > 0 ? "evalRegression" : ""}>{dDur > 0 ? "+" : ""}{dDur.toFixed(0)} ms</strong></article>
                      <article className="metricCard"><span>Tokens</span><strong className={dTok > 0 ? "evalRegression" : ""}>{dTok > 0 ? "+" : ""}{dTok}</strong></article>
                      <article className="metricCard"><span>Status match</span><strong>{a.status === b.status ? "Same" : "Different"}</strong></article>
                    </div>
                  </div>
                );
              })()}
            </article>
          </section>
        ) : loading ? (
          <div className="emptyPanel">
            <p>Loading run detail...</p>
          </div>
        ) : !selectedRun ? (
          <div className="emptyPanel">
            <p>Select a run when generation records are available.</p>
          </div>
        ) : (
          <section className="detailStack">
            <article className="panel detailPanel">
              <div className="previewHeader">
                <div>
                  <p className="kicker">Selected run</p>
                  <h2 className="sectionTitle">{selectedRun.company_name}</h2>
                </div>
                <span className={`statusChip ${selectedRun.status === "completed" ? "statusReady" : "statusError"}`}>
                  {selectedRun.status}
                </span>
              </div>

              <div className="metricGrid metricGridThree compactMetrics">
                <article className="metricCard">
                  <span>Total duration</span>
                  <strong>{selectedRun.total_duration_ms?.toFixed(2) ?? "-"} ms</strong>
                </article>
                <article className="metricCard">
                  <span>LLM duration</span>
                  <strong>{selectedRun.llm_duration_ms?.toFixed(2) ?? "-"} ms</strong>
                </article>
                <article className="metricCard">
                  <span>Total tokens</span>
                  <strong>{selectedRun.total_tokens ?? "-"}</strong>
                </article>
              </div>

              <div className="metricGrid metricGridThree compactMetrics">
                <article className="metricCard">
                  <span>Model</span>
                  <strong>{selectedRun.model_name ?? "-"}</strong>
                </article>
                <article className="metricCard">
                  <span>Prompt tokens</span>
                  <strong>{selectedRun.input_tokens ?? "-"}</strong>
                </article>
                <article className="metricCard">
                  <span>Output tokens</span>
                  <strong>{selectedRun.output_tokens ?? "-"}</strong>
                </article>
              </div>

              <div className="promptPanel">
                <p className="miniLabel">Prompt preview</p>
                <p>
                  {selectedRun.prompt_preview ??
                    "No prompt preview captured for this run."}
                </p>
              </div>

              <div className="promptPanel">
                <p className="miniLabel">LangSmith trace</p>
                <p>
                  {selectedRun.langsmith_project
                    ? `Project: ${selectedRun.langsmith_project}`
                    : "No LangSmith project recorded for this run."}
                </p>
                {selectedRun.langsmith_trace_url ? (
                  <a className="textLink" href={selectedRun.langsmith_trace_url} rel="noreferrer" target="_blank">
                    Open LangSmith trace
                  </a>
                ) : null}
              </div>

              {selectedRun.error ? <p className="errorText">{selectedRun.error}</p> : null}

              {selectedRun.microsite_slug ? (
                <div className="actionRow">
                  <Link className="buttonPrimary" href={`/microsites/${selectedRun.microsite_slug}`}>
                    Open generated microsite
                  </Link>
                  <Link className="buttonSecondary" href="/microsites">
                    Back to library
                  </Link>
                </div>
              ) : null}
            </article>

            <div className="splitDetailGrid">
              <article className="panel detailPanel">
                <div className="panelHeader compactHeader">
                  <div>
                    <p className="kicker">Step trace</p>
                    <h2 className="sectionTitle">Pipeline timings</h2>
                  </div>
                </div>

                <div className="stepList">
                  {selectedRun.steps.map((step) => (
                    <article className="stepItem" key={`${step.name}-${step.started_at}`}>
                      <div className="stepHead">
                        <strong>{step.name}</strong>
                        <span>{step.duration_ms.toFixed(2)} ms</span>
                      </div>
                      <p className="stepStatus">{step.status}</p>
                      {Object.keys(step.metadata).length > 0 ? (
                        <pre className="stepMeta">{JSON.stringify(step.metadata, null, 2)}</pre>
                      ) : null}
                    </article>
                  ))}
                </div>
              </article>

              <article className="panel detailPanel">
                <div className="panelHeader compactHeader">
                  <div>
                    <p className="kicker">LangSmith</p>
                    <h2 className="sectionTitle">Hosted tracing</h2>
                  </div>
                </div>

                {!langsmith ? (
                  <div className="emptyPanel">
                    <p>LangSmith status unavailable.</p>
                  </div>
                ) : (
                  <div className="detailStack">
                    <div className="promptPanel">
                      <p className="miniLabel">Project</p>
                      <p>{langsmith.project_name ?? "Not configured"}</p>
                      {langsmith.project_url ? (
                        <a className="textLink" href={langsmith.project_url} rel="noreferrer" target="_blank">
                          Open LangSmith project
                        </a>
                      ) : null}
                    </div>

                     <div className="requestList">
                       {langsmith.recent_runs.map((run) => (
                         <article className="requestItem" key={run.id}>
                           <div className="requestInfo">
                             <p className="miniLabel">{run.run_type ?? "trace"}</p>
                             <strong>{run.name ?? run.id}</strong>
                             <p>{run.start_time ? new Date(run.start_time).toLocaleString() : "Unknown time"}</p>
                             {run.error_message ? <p className="errorText">{run.error_message}</p> : null}
                             {run.failed_steps.length > 0 ? (
                               <div className="stepList compactStepList">
                                 {run.failed_steps.map((step) => (
                                   <article className="stepItem" key={step.id}>
                                     <div className="stepHead">
                                       <strong>{step.name ?? step.id}</strong>
                                       <span>{step.run_type ?? "step"}</span>
                                     </div>
                                     <p className="stepStatus">{step.error_message}</p>
                                   </article>
                                 ))}
                               </div>
                             ) : null}
                           </div>
                           <div className="requestMeta">
                             <span>{run.status ?? "unknown"}</span>
                             {run.url ? (
                              <a className="textLink" href={run.url} rel="noreferrer" target="_blank">
                                Open
                              </a>
                            ) : null}
                          </div>
                        </article>
                      ))}
                    </div>
                  </div>
                )}
              </article>

              <article className="panel detailPanel">
                <div className="panelHeader compactHeader">
                  <div>
                    <p className="kicker">Request ledger</p>
                    <h2 className="sectionTitle">Latest backend calls</h2>
                  </div>
                </div>

                <div className="requestList">
                  {requests.map((request) => (
                    <article className="requestItem" key={request.id}>
                      <div className="requestInfo">
                        <p className="miniLabel">{request.method}</p>
                        <strong>{request.path}</strong>
                        <p>{new Date(request.occurred_at).toLocaleString()}</p>
                      </div>
                      <div className="requestMeta">
                        <span>Status {request.status_code}</span>
                        <strong>{request.duration_ms.toFixed(2)} ms</strong>
                      </div>
                    </article>
                  ))}
                </div>
              </article>
            </div>
          </section>
        )}
      </section>
    </main>
  );
}
