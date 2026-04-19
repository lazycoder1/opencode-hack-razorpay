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

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function ObservabilityPage() {
  const [runs, setRuns] = useState<GenerationRun[]>([]);
  const [requests, setRequests] = useState<ApiRequestEvent[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadObservability() {
      try {
        const [runsResponse, requestsResponse] = await Promise.all([
          fetch(`${apiBaseUrl}/api/observability/runs`),
          fetch(`${apiBaseUrl}/api/observability/requests`),
        ]);

        if (!runsResponse.ok) {
          throw new Error(`Unable to load runs: ${runsResponse.status}`);
        }

        if (!requestsResponse.ok) {
          throw new Error(`Unable to load requests: ${requestsResponse.status}`);
        }

        const runsData: GenerationRun[] = await runsResponse.json();
        const requestsData: ApiRequestEvent[] = await requestsResponse.json();
        setRuns(runsData);
        setRequests(requestsData);
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
        <div className="brandMark">
          <div className="brandGlyph">OB</div>
          <div className="brandCopy">
            <strong>Observability Deck</strong>
            <span>Runs, prompts, and latency</span>
          </div>
        </div>
        <div className="topbarNav">
          <Link href="/">Create</Link>
          <Link href="/microsites">Microsites</Link>
        </div>
      </nav>

      <section className="pageHeader">
        <div>
          <p className="eyebrow">Operator surface</p>
          <h1 className="pageTitle">Keep the generation trail visible.</h1>
        </div>
        <div className="heroMeta">
          <div className="metaItem">
            <span>Completed runs</span>
            <strong>{completedRuns}</strong>
          </div>
          <div className="metaItem">
            <span>Failed runs</span>
            <strong>{failedRuns}</strong>
          </div>
          <div className="metaItem">
            <span>Avg request latency</span>
            <strong>{averageLatency?.toFixed(1) ?? "-"} ms</strong>
          </div>
        </div>
      </section>

      {error ? <p className="errorText">{error}</p> : null}

      <section className="operatorGrid">
        <aside className="operatorRail">
          <div className="panelHeader">
            <p className="eyebrowCool">Runs</p>
            <p className="bodyText">Select a generation trace to inspect duration, token usage, prompt preview, and step timings.</p>
          </div>

          {runs.length === 0 ? (
            <div className="emptyState">
              <p>No runs captured yet.</p>
            </div>
          ) : (
            <div className="selectionList">
              {runs.map((run) => (
                <button
                  key={run.id}
                  className={`runButton ${run.id === selectedRun?.id ? "active" : ""}`}
                  onClick={() => setSelectedRunId(run.id)}
                  type="button"
                >
                  <div>
                    <span>{run.status}</span>
                    <strong>{run.company_name}</strong>
                    <p>{new Date(run.started_at).toLocaleString()}</p>
                  </div>
                  <strong>{run.total_duration_ms?.toFixed(0) ?? "-"} ms</strong>
                </button>
              ))}
            </div>
          )}
        </aside>

        {!selectedRun ? (
          <div className="emptyState">
            <p>Select a run once traces are available.</p>
          </div>
        ) : (
          <section className="operatorLayout">
            <article className="operatorDetail">
              <div className="operatorMeta">
                <div>
                  <p className="eyebrowCool">Run detail</p>
                  <h2 className="spotlightTitle">{selectedRun.company_name}</h2>
                </div>
                <div className="statusPills">
                  <div className={`statusPill ${selectedRun.status === "completed" ? "success" : "danger"}`}>
                    {selectedRun.status}
                  </div>
                </div>
              </div>

              <div className="metricsRow metricGrid">
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

              <div className="operatorStacks">
                <div className="requestStack">
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

                {selectedRun.prompt_preview ? (
                  <div className="promptPreview">
                    <p className="eyebrow">Prompt preview</p>
                    <p className="operatorBody">{selectedRun.prompt_preview}</p>
                  </div>
                ) : (
                  <div className="promptPreview">
                    <p className="eyebrow">Prompt preview</p>
                    <p className="operatorBody">No prompt preview captured for this run.</p>
                  </div>
                )}
              </div>

              {selectedRun.error ? <p className="errorText">{selectedRun.error}</p> : null}

              <div className="timelineList">
                {selectedRun.steps.map((step) => (
                  <article className="stepCard" key={`${step.name}-${step.started_at}`}>
                    <div className="stepTop">
                      <strong>{step.name}</strong>
                      <time>{step.duration_ms.toFixed(2)} ms</time>
                    </div>
                    <p className="summaryTime">{step.status}</p>
                    {Object.keys(step.metadata).length > 0 ? (
                      <pre className="stepMeta">{JSON.stringify(step.metadata, null, 2)}</pre>
                    ) : null}
                  </article>
                ))}
              </div>

              {selectedRun.microsite_slug ? (
                <div className="stackActions">
                  <Link className="buttonPrimary" href={`/microsites/${selectedRun.microsite_slug}`}>
                    Open generated microsite
                  </Link>
                  <Link className="buttonGhost" href="/microsites">
                    Back to microsite library
                  </Link>
                </div>
              ) : null}
            </article>

            <article className="panel">
              <div className="panelHeader">
                <p className="eyebrow">API ledger</p>
                <h2 className="spotlightTitle">Latest backend requests</h2>
              </div>

              <div className="requestStack">
                {requests.map((request) => (
                  <article className="requestCard" key={request.id}>
                    <div>
                      <p className="summaryLabel">{request.method}</p>
                      <strong>{request.path}</strong>
                      <time>{new Date(request.occurred_at).toLocaleString()}</time>
                    </div>
                    <div className="requestStats">
                      <span>Status {request.status_code}</span>
                      <strong>{request.duration_ms.toFixed(2)} ms</strong>
                    </div>
                  </article>
                ))}
              </div>
            </article>
          </section>
        )}
      </section>
    </main>
  );
}
