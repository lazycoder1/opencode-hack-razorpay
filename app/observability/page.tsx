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

  useEffect(() => {
    async function loadObservability() {
      try {
        const [runsResponse, requestsResponse, langsmithResponse] = await Promise.all([
          fetch(`${apiBaseUrl}/api/observability/runs`),
          fetch(`${apiBaseUrl}/api/observability/requests`),
          fetch(`${apiBaseUrl}/api/observability/langsmith`),
        ]);

        if (!runsResponse.ok) {
          throw new Error(`Unable to load runs: ${runsResponse.status}`);
        }

        if (!requestsResponse.ok) {
          throw new Error(`Unable to load requests: ${requestsResponse.status}`);
        }

        if (!langsmithResponse.ok) {
          throw new Error(`Unable to load LangSmith status: ${langsmithResponse.status}`);
        }

        const runsData: GenerationRun[] = await runsResponse.json();
        const requestsData: ApiRequestEvent[] = await requestsResponse.json();
        const langsmithData: LangSmithStatus = await langsmithResponse.json();
        setRuns(runsData);
        setRequests(requestsData);
        setLangsmith(langsmithData);
        setSelectedRunId(runsData[0]?.id ?? "");
      } catch (caughtError) {
        setError(caughtError instanceof Error ? caughtError.message : "Unable to load observability data");
      }
    }

    void loadObservability();
  }, []);

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? runs[0] ?? null,
    [runs, selectedRunId],
  );

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

      {error ? <p className="errorText">{error}</p> : null}

      <section className="opsGrid">
        <aside className="panel selectorPanel">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Runs</p>
              <h2 className="sectionTitle">Generation history</h2>
            </div>
          </div>

          {runs.length === 0 ? (
            <div className="emptyPanel">
              <p>No runs captured yet.</p>
            </div>
          ) : (
            <div className="selectorList">
              {runs.map((run) => (
                <button
                  key={run.id}
                  className={`selectorButton ${run.id === selectedRun?.id ? "active" : ""}`}
                  onClick={() => setSelectedRunId(run.id)}
                  type="button"
                >
                  <div className="selectorTop">
                    <span>{run.status}</span>
                    <strong>{run.total_duration_ms?.toFixed(0) ?? "-"} ms</strong>
                  </div>
                  <strong className="selectorTitle">{run.company_name}</strong>
                  <p>{new Date(run.started_at).toLocaleString()}</p>
                </button>
              ))}
            </div>
          )}
        </aside>

        {!selectedRun ? (
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
