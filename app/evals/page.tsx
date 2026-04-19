"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type Check = {
  name: string;
  description: string;
  passed: boolean;
};

type EvalCase = {
  name: string;
  prospect: string;
  source_company: string;
  checks: { name: string; description: string }[];
};

type EvalResult = {
  id: string;
  eval_name: string;
  prospect: string;
  source_company: string;
  status: string;
  checks: Check[];
  passed: number;
  failed: number;
  total: number;
  council_run_id: string | null;
  duration_ms: number | null;
  created_at: string;
};

export default function EvalsPage() {
  const [cases, setCases] = useState<EvalCase[]>([]);
  const [results, setResults] = useState<EvalResult[]>([]);
  const [running, setRunning] = useState(false);
  const [runningCase, setRunningCase] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagnosis, setDiagnosis] = useState<{ check_name: string; likely_cause: string; fix: string }[] | null>(null);
  const [promptPatch, setPromptPatch] = useState<string | null>(null);
  const [applyingFix, setApplyingFix] = useState(false);
  const [fixApplied, setFixApplied] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch(`${apiBaseUrl}/api/evals/cases`).then((r) => r.json()),
      fetch(`${apiBaseUrl}/api/evals/results`).then((r) => r.json()),
    ])
      .then(([casesData, resultsData]) => {
        setCases(casesData);
        setResults(resultsData);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load eval data"));
  }, []);

  async function runSingleCase(caseName: string) {
    setRunningCase(caseName);
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/evals/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_name: caseName }),
      });
      if (!response.ok) throw new Error(`Eval failed: ${response.status}`);
      const newResults: EvalResult[] = await response.json();
      setResults((prev) => [...newResults, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Eval run failed");
    } finally {
      setRunningCase(null);
    }
  }

  async function runAllCases() {
    setRunning(true);
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/evals/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!response.ok) throw new Error(`Eval suite failed: ${response.status}`);
      const newResults: EvalResult[] = await response.json();
      setResults((prev) => [...newResults, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Eval suite failed");
    } finally {
      setRunning(false);
    }
  }

  async function diagnoseFailures() {
    const failedChecks = results
      .flatMap((r) => r.checks.filter((c) => !c.passed).map((c) => c.name))
      .filter((v, i, a) => a.indexOf(v) === i);
    if (failedChecks.length === 0) { setError("No failures to diagnose"); return; }
    const sample = results.find((r) => r.failed > 0);
    setDiagnosing(true);
    setDiagnosis(null);
    setPromptPatch(null);
    setFixApplied(false);
    try {
      const response = await fetch(`${apiBaseUrl}/api/evals/diagnose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          failed_checks: failedChecks,
          prospect: sample?.prospect ?? "",
          source_company: sample?.source_company ?? "",
        }),
      });
      if (!response.ok) throw new Error(`Diagnosis failed: ${response.status}`);
      const data = await response.json();
      setDiagnosis(data.suggestions?.diagnosis ?? []);
      setPromptPatch(data.suggestions?.prompt_patch ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Diagnosis failed");
    } finally {
      setDiagnosing(false);
    }
  }

  async function applyPromptFix() {
    if (!promptPatch) return;
    setApplyingFix(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/evals/apply-fix`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt_patch: promptPatch }),
      });
      if (!response.ok) throw new Error(`Apply fix failed: ${response.status}`);
      setFixApplied(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Apply fix failed");
    } finally {
      setApplyingFix(false);
    }
  }

  const totalPassed = results.reduce((s, r) => s + r.passed, 0);
  const totalFailed = results.reduce((s, r) => s + r.failed, 0);
  const totalChecks = totalPassed + totalFailed;
  const passRate = totalChecks > 0 ? ((totalPassed / totalChecks) * 100).toFixed(1) : "-";
  const regressions = results.filter((r) => r.status === "regression").length;
  const qualityGates = results.filter((r) => r.eval_name.startsWith("quality_gate_"));
  const manualEvals = results.filter((r) => !r.eval_name.startsWith("quality_gate_"));

  return (
    <main className="pageShell">
      <nav className="topbar">
        <div className="brand">
          <div className="brandIcon">EV</div>
          <div className="brandBlock">
            <strong className="brandTitle">Eval Pipeline</strong>
            <span className="brandCaption">Named tests and quality gates</span>
          </div>
        </div>
        <div className="navCluster">
          <Link className="navLink" href="/">Create</Link>
          <Link className="navLink" href="/sandbox">Sandbox</Link>
          <Link className="navLink" href="/observability">Observability</Link>
        </div>
      </nav>

      <section className="pageIntro">
        <div>
          <p className="kicker">Evaluation and iteration</p>
          <h1 className="pageTitle">Named eval set with automated quality gates.</h1>
          <p className="sectionText">
            5 named test cases run the full council pipeline and check output against assertions.
            Quality gates run automatically after every generation and flag regressions.
          </p>
        </div>

        <div className="metricGrid metricGridFour compactMetrics">
          <article className="metricCard">
            <span>Pass rate</span>
            <strong>{passRate}%</strong>
          </article>
          <article className="metricCard">
            <span>Total checks</span>
            <strong>{totalPassed}/{totalChecks}</strong>
          </article>
          <article className="metricCard">
            <span>Regressions</span>
            <strong className={regressions > 0 ? "evalRegression" : ""}>{regressions}</strong>
          </article>
          <article className="metricCard">
            <span>Quality gates</span>
            <strong>{qualityGates.length}</strong>
          </article>
        </div>
      </section>

      {error ? <p className="errorText">{error}</p> : null}

      {diagnosis ? (
        <section className="panel diagnosisPanel">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Closed-loop auto-remediation</p>
              <h2 className="sectionTitle">AI diagnosis of {diagnosis.length} failure{diagnosis.length !== 1 ? "s" : ""}</h2>
            </div>
            <div className="evalCaseActions">
              {promptPatch ? (
                <button className="buttonPrimary" type="button" disabled={applyingFix || fixApplied} onClick={applyPromptFix}>
                  {fixApplied ? "Fix applied — re-run evals" : applyingFix ? "Applying..." : "Apply prompt fix"}
                </button>
              ) : null}
              <button className="buttonSecondary" type="button" onClick={() => { setDiagnosis(null); setPromptPatch(null); }}>Dismiss</button>
            </div>
          </div>
          <div className="diagnosisList">
            {diagnosis.map((d, i) => (
              <div className="diagnosisCard" key={i}>
                <div className="diagnosisHeader">
                  <span className="evalCheckDot evalFail" />
                  <strong>{d.check_name}</strong>
                </div>
                <p className="diagnosisCause"><strong>Likely cause:</strong> {d.likely_cause}</p>
                <p className="diagnosisFix"><strong>Fix:</strong> {d.fix}</p>
              </div>
            ))}
          </div>
          {promptPatch ? (
            <div className="promptPanel">
              <p className="miniLabel">Suggested prompt patch</p>
              <pre className="stepMeta">{promptPatch}</pre>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="evalGrid">
        <article className="panel evalCasesPanel">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Named eval set</p>
              <h2 className="sectionTitle">5 test cases</h2>
            </div>
            <div className="evalCaseActions">
              <button className="buttonSecondary" type="button" disabled={diagnosing || totalFailed === 0} onClick={diagnoseFailures}>
                {diagnosing ? "Diagnosing..." : "Diagnose failures"}
              </button>
              <button className="buttonPrimary" type="button" disabled={running || runningCase !== null} onClick={runAllCases}>
                {running ? "Running all..." : "Run all evals"}
              </button>
            </div>
          </div>

          <div className="evalCaseList">
            {cases.map((c) => {
              const latestResult = results.find((r) => r.eval_name === c.name);
              const isRunning = runningCase === c.name;

              return (
                <div className="evalCaseCard" key={c.name}>
                  <div className="evalCaseTop">
                    <div>
                      <strong>{c.source_company} x {c.prospect}</strong>
                      <span className="evalCaseName">{c.name}</span>
                    </div>
                    <div className="evalCaseActions">
                      {latestResult ? (
                        <span className={`statusChip ${latestResult.status === "passed" ? "statusReady" : "statusError"}`}>
                          {latestResult.passed}/{latestResult.total} {latestResult.status}
                        </span>
                      ) : null}
                      <button
                        className="buttonSecondary"
                        type="button"
                        disabled={isRunning || running}
                        onClick={() => runSingleCase(c.name)}
                      >
                        {isRunning ? "Running..." : "Run"}
                      </button>
                    </div>
                  </div>

                  <div className="evalCheckList">
                    {c.checks.map((check) => {
                      const checkResult = latestResult?.checks.find((cr) => cr.name === check.name);
                      return (
                        <div className="evalCheckItem" key={check.name}>
                          <span className={`evalCheckDot ${checkResult ? (checkResult.passed ? "evalPass" : "evalFail") : ""}`} />
                          <span>{check.description}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </article>

        <article className="panel evalResultsPanel">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Run history</p>
              <h2 className="sectionTitle">Quality gates and manual runs</h2>
            </div>
          </div>

          {qualityGates.length > 0 ? (
            <div className="evalSection">
              <p className="kicker">Automated quality gates</p>
              <div className="evalResultList">
                {qualityGates.slice(0, 20).map((r) => (
                  <div className={`evalResultCard ${r.status === "regression" ? "evalResultRegression" : ""}`} key={r.id}>
                    <div className="evalResultTop">
                      <div>
                        <strong>{r.source_company} x {r.prospect}</strong>
                        <span className={`statusChip ${r.status === "passed" ? "statusReady" : "statusError"}`}>
                          {r.status === "regression" ? "REGRESSION" : r.status}
                        </span>
                      </div>
                      <span className="evalResultMeta">{r.passed}/{r.total} checks</span>
                    </div>
                    <div className="evalCheckList evalCheckListCompact">
                      {r.checks.map((check, i) => (
                        <div className="evalCheckItem" key={`${check.name}-${i}`}>
                          <span className={`evalCheckDot ${check.passed ? "evalPass" : "evalFail"}`} />
                          <span>{check.name}</span>
                        </div>
                      ))}
                    </div>
                    <span className="evalResultDate">{new Date(r.created_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {manualEvals.length > 0 ? (
            <div className="evalSection">
              <p className="kicker">Manual eval runs</p>
              <div className="evalResultList">
                {manualEvals.slice(0, 20).map((r) => (
                  <div className="evalResultCard" key={r.id}>
                    <div className="evalResultTop">
                      <div>
                        <strong>{r.source_company} x {r.prospect}</strong>
                        <span className={`statusChip ${r.status === "passed" ? "statusReady" : "statusError"}`}>
                          {r.passed}/{r.total} {r.status}
                        </span>
                      </div>
                      <span className="evalResultMeta">
                        {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : ""}
                      </span>
                    </div>
                    <div className="evalCheckList evalCheckListCompact">
                      {r.checks.map((check, i) => (
                        <div className="evalCheckItem" key={`${check.name}-${i}`}>
                          <span className={`evalCheckDot ${check.passed ? "evalPass" : "evalFail"}`} />
                          <span>{check.name}</span>
                        </div>
                      ))}
                    </div>
                    <span className="evalResultDate">{new Date(r.created_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {results.length === 0 ? (
            <div className="emptyPanel">
              <p>No eval results yet. Run the eval set or generate a microsite to trigger a quality gate.</p>
            </div>
          ) : null}
        </article>
      </section>
    </main>
  );
}
