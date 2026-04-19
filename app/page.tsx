"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type AgentStep = {
  step_name: string;
  agent_role: string;
  status: string;
  duration_ms: number;
  cost_usd: number | null;
  model_name: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
};

type CouncilRun = {
  run_id: string;
  prospect: string;
  source_company: string;
  status: string;
  total_duration_ms: number;
  total_cost_usd: number;
  steps: AgentStep[];
  final_html: string;
  seller_research: string;
  prospect_research: string;
};

type ProspectState = {
  name: string;
  status: "queued" | "running" | "completed" | "failed";
  currentStep: string;
  run: CouncilRun | null;
  slug: string;
};

type CompanyProfile = {
  id: string;
  name: string;
  summary: string;
};

const STEP_LABELS: Record<string, string> = {
  manager_plan: "Planning",
  seller_research: "Researching seller",
  seller_research_base: "Researching seller",
  seller_research_mcp: "Enmovil KB lookup",
  prospect_research: "Researching prospect",
  prospect_seller_fit: "Mapping pain to wedges",
  manager_review: "Reviewing research",
  narrative_brief: "Editing narrative",
  generate_microsite: "Generating microsite",
};

const AGENT_LABELS: Record<string, string> = {
  manager: "Manager",
  seller_researcher: "Seller Researcher",
  prospect_researcher: "Prospect Researcher",
  fit_analyst: "Fit Analyst",
  generator: "Generator",
};

const MAX_PARALLEL_RUNS = 3;

export default function Home() {
  const [companyProfiles, setCompanyProfiles] = useState<CompanyProfile[]>([]);
  const [sourceCompanyId, setSourceCompanyId] = useState("razorpay");
  const [prospectInput, setProspectInput] = useState("Zepto\nSwiggy\nCRED");
  const [prospects, setProspects] = useState<ProspectState[]>([]);
  const [running, setRunning] = useState(false);
  const [selectedProspect, setSelectedProspect] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [companyProfilesError, setCompanyProfilesError] = useState("");
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const abortRef = useRef(false);

  const prospectNames = prospectInput
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  const completedCount = prospects.filter((p) => p.status === "completed").length;
  const failedCount = prospects.filter((p) => p.status === "failed").length;
  const runningCount = prospects.filter((p) => p.status === "running").length;
  const totalCost = prospects.reduce((s, p) => s + (p.run?.total_cost_usd ?? 0), 0);
  const totalDuration = prospects.reduce((s, p) => s + (p.run?.total_duration_ms ?? 0), 0);

  const selected = prospects.find((p) => p.name === selectedProspect) ?? null;
  const selectedSourceCompany = companyProfiles.find((profile) => profile.id === sourceCompanyId) ?? null;

  useEffect(() => {
    async function loadCompanyProfiles() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/company-profiles`);
        if (!response.ok) {
          throw new Error(`Unable to load company profiles: ${response.status}`);
        }

        const data: CompanyProfile[] = await response.json();
        setCompanyProfiles(data);
        setSourceCompanyId((currentId) => {
          if (data.some((profile) => profile.id === currentId)) {
            return currentId;
          }

          return data.find((profile) => profile.id === "razorpay")?.id ?? data[0]?.id ?? "";
        });
      } catch (caughtError) {
        setCompanyProfilesError(caughtError instanceof Error ? caughtError.message : "Unable to load company profiles");
      }
    }

    void loadCompanyProfiles();
  }, []);

  async function runBatch() {
    if (prospectNames.length === 0 || !selectedSourceCompany) return;

    const sourceCompanyName = selectedSourceCompany.name;

    setRunning(true);
    setError("");
    abortRef.current = false;

    const initial: ProspectState[] = prospectNames.map((name) => ({
      name,
      status: "queued",
      currentStep: "",
      run: null,
      slug: "",
    }));
    setProspects(initial);
    setSelectedProspect(null);

    let nextIndex = 0;

    async function runProspect(index: number) {
      const prospect = initial[index];

      setProspects((prev) => prev.map((p, idx) => (idx === index ? { ...p, status: "running", currentStep: "manager_plan" } : p)));

      try {
        const response = await fetch(`${apiBaseUrl}/api/council/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prospect: prospect.name,
            source_company: sourceCompanyName,
          }),
        });

        if (!response.ok) {
          throw new Error(`Failed for ${prospect.name}: ${response.status}`);
        }

        const run: CouncilRun = await response.json();
        const slug = `${sourceCompanyName.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-x-${prospect.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${run.run_id.slice(0, 6)}`;

        setProspects((prev) =>
          prev.map((p, idx) =>
            idx === index
              ? { ...p, status: run.status === "completed" ? "completed" : "failed", currentStep: "", run, slug }
              : p,
          ),
        );

        if (run.status === "completed" && run.final_html) {
          setSelectedProspect((current) => current ?? prospect.name);
        }
      } catch (caughtError) {
        setProspects((prev) =>
          prev.map((p, idx) => (idx === index ? { ...p, status: "failed", currentStep: "" } : p)),
        );
        setError((current) => current || (caughtError instanceof Error ? caughtError.message : `Failed for ${prospect.name}`));
      }
    }

    async function worker() {
      while (!abortRef.current) {
        const index = nextIndex;
        nextIndex += 1;

        if (index >= initial.length) {
          return;
        }

        await runProspect(index);
      }
    }

    const workerCount = Math.min(MAX_PARALLEL_RUNS, initial.length);
    await Promise.all(Array.from({ length: workerCount }, () => worker()));

    setRunning(false);
  }

  return (
    <main className="pageShell">
      <nav className="topbar">
        <div className="brand">
          <div className="brandIcon">CA</div>
          <div className="brandBlock">
            <strong className="brandTitle">Council of Agents</strong>
            <span className="brandCaption">Batch microsite generation</span>
          </div>
        </div>
        <div className="navCluster">
          <Link className="navLink" href="/sandbox">Sandbox</Link>
          <Link className="navLink" href="/evals">Evals</Link>
          <Link className="navLink" href="/observability">Observability</Link>
        </div>
      </nav>

      <section className="demoInputSection">
        <div className="demoInputGrid">
          <div className="demoInputLeft">
            <p className="kicker">Generate microsites</p>
            <h1 className="demoTitle">Type prospects. Hit generate. Agents do the rest.</h1>
            <p className="sectionText">
              A council of 5 agents researches your company, researches each prospect, reviews the research quality, and generates a unique HTML microsite per prospect.
            </p>
          </div>

          <div className="demoInputRight">
            <label className="fieldStack">
              <div className="fieldTop">
                <strong>Your company (seller)</strong>
              </div>
              <select
                className="companySelect"
                value={sourceCompanyId}
                onChange={(e) => setSourceCompanyId(e.target.value)}
                disabled={running || companyProfiles.length === 0}
              >
                {companyProfiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
              {selectedSourceCompany ? <span className="fieldHint">{selectedSourceCompany.summary}</span> : null}
            </label>

            <label className="fieldStack">
              <div className="fieldTop">
                <strong>Prospects</strong>
                <span className="fieldHint">{prospectNames.length} companies</span>
              </div>
              <textarea
                className="demoTextarea"
                value={prospectInput}
                onChange={(e) => setProspectInput(e.target.value)}
                placeholder={"Zepto\nSwiggy\nCRED"}
                disabled={running}
              />
            </label>

            <button
              className="buttonPrimary demoButton"
              type="button"
              disabled={running || prospectNames.length === 0 || !selectedSourceCompany}
              onClick={runBatch}
            >
              {running
                ? `Generating ${completedCount + failedCount}/${prospects.length} complete${runningCount > 0 ? ` · ${runningCount} running` : ""}`
                : `Generate ${prospectNames.length} microsites`}
            </button>
          </div>
        </div>
      </section>

      {companyProfilesError ? <p className="errorText">{companyProfilesError}</p> : null}

      {prospects.length > 0 ? (
        <section className="demoProgress">
          <div className="demoStats">
            <div className="metricGrid metricGridFour compactMetrics">
              <article className="metricCard">
                <span>Completed</span>
                <strong>{completedCount} / {prospects.length}</strong>
              </article>
              <article className="metricCard">
                <span>Failed</span>
                <strong>{failedCount}</strong>
              </article>
              <article className="metricCard">
                <span>Total cost</span>
                <strong>${totalCost.toFixed(4)}</strong>
              </article>
              <article className="metricCard">
                <span>Total time</span>
                <strong>{(totalDuration / 1000).toFixed(1)}s</strong>
              </article>
            </div>
          </div>

          <div className="demoProspectList">
            {prospects.map((p) => (
              <button
                key={p.name}
                className={`demoProspectCard ${p.name === selectedProspect ? "active" : ""} ${p.status}`}
                type="button"
                onClick={() => p.run ? setSelectedProspect(p.name) : undefined}
                disabled={!p.run}
              >
                <div className="demoProspectTop">
                    <strong>{selectedSourceCompany?.name ?? "Seller"} x {p.name}</strong>
                  <span className={`statusChip ${p.status === "completed" ? "statusReady" : p.status === "failed" ? "statusError" : p.status === "running" ? "statusPending" : ""}`}>
                    {p.status === "running" ? (STEP_LABELS[p.currentStep] || "Running...") : p.status}
                  </span>
                </div>

                {p.status === "running" ? (
                  <div className="demoProspectProgress">
                    <div className="sandboxSpinner demoSpinner" />
                    <span>{STEP_LABELS[p.currentStep] || "Processing..."}</span>
                  </div>
                ) : null}

                {p.run ? (
                  <div className="demoProspectMeta">
                    <span>{(p.run.total_duration_ms / 1000).toFixed(1)}s</span>
                    <span>${p.run.total_cost_usd.toFixed(4)}</span>
                    <span>{p.run.steps.length} agents</span>
                    {p.slug ? <span className="demoSlug">/m/{p.slug}</span> : null}
                  </div>
                ) : null}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {error ? <p className="errorText">{error}</p> : null}

      {selected?.run?.final_html ? (
        <section className="demoPreview">
          <div className="previewHeader">
            <div>
              <p className="kicker">{selectedSourceCompany?.name ?? "Seller"} x {selected.name}</p>
              <h2 className="sectionTitle">Generated microsite</h2>
            </div>
            <div className="navCluster">
              {selected.slug ? (
                <a className="buttonPrimary" href={`${apiBaseUrl}/m/${selected.slug}`} target="_blank" rel="noopener noreferrer">
                  Open live URL
                </a>
              ) : null}
              <button className="buttonTertiary" type="button" onClick={() => {
                const blob = new Blob([selected.run!.final_html], { type: "text/html" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `${(selectedSourceCompany?.name ?? "seller").toLowerCase()}-x-${selected.name.toLowerCase()}.html`;
                a.click();
                URL.revokeObjectURL(url);
              }}>
                Download HTML
              </button>
            </div>
          </div>

          <div className="frameShell demoFrame">
            <div className="frameBar">
              <div className="browserDots"><span /><span /><span /></div>
              <div className="frameAddress">/m/{selected.slug}</div>
              <div className="frameRoute">{selected.run.status}</div>
            </div>
            <iframe
              ref={iframeRef}
              className="sandboxIframe"
              srcDoc={selected.run.final_html}
              sandbox="allow-scripts allow-same-origin"
              title={`${selectedSourceCompany?.name ?? "Seller"} x ${selected.name}`}
            />
          </div>

          <div className="demoTrace">
            <p className="kicker">Agent trace</p>
            <div className="demoTraceGrid">
              {selected.run.steps.map((step, i) => (
                <div className="demoTraceStep" key={`${step.step_name}-${i}`}>
                  <div className="demoTraceStepTop">
                    <strong>{STEP_LABELS[step.step_name] ?? step.step_name}</strong>
                    <span className="stepAgentBadge">{AGENT_LABELS[step.agent_role] ?? step.agent_role}</span>
                  </div>
                  <div className="demoTraceStepMeta">
                    <span>{step.duration_ms.toFixed(0)}ms</span>
                    {step.cost_usd !== null ? <span>${step.cost_usd.toFixed(4)}</span> : null}
                    <span>{step.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </main>
  );
}
