"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type StageKey = "manager_plan" | "seller_research" | "prospect_research" | "manager_review" | "generate_microsite";

type PromptPair = { system: string; user: string };

type AgentStep = {
  step_name: string;
  agent_role: string;
  status: string;
  started_at: string;
  duration_ms: number;
  output: string;
  model_name: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  cost_usd: number | null;
  metadata: Record<string, unknown>;
};

type CouncilRun = {
  run_id: string;
  prospect: string;
  source_company: string;
  status: string;
  started_at: string;
  completed_at: string;
  total_duration_ms: number;
  total_cost_usd: number;
  steps: AgentStep[];
  seller_research: string;
  prospect_research: string;
  generation_plan: string;
  review_notes: string;
  final_html: string;
};

const STAGES: { key: StageKey; label: string; agent: string }[] = [
  { key: "manager_plan", label: "1. Manager Plan", agent: "Manager" },
  { key: "seller_research", label: "2. Seller Research", agent: "Seller Researcher" },
  { key: "prospect_research", label: "3. Prospect Research", agent: "Prospect Researcher" },
  { key: "manager_review", label: "4. Manager Review", agent: "Manager" },
  { key: "generate_microsite", label: "5. Generate Microsite", agent: "Generator" },
];

export default function SandboxPage() {
  const [prospect, setProspect] = useState("Zepto");
  const [sourceCompany, setSourceCompany] = useState("Razorpay");
  const [prompts, setPrompts] = useState<Record<StageKey, PromptPair>>({
    manager_plan: { system: "", user: "" },
    seller_research: { system: "", user: "" },
    prospect_research: { system: "", user: "" },
    manager_review: { system: "", user: "" },
    generate_microsite: { system: "", user: "" },
  });
  const [defaults, setDefaults] = useState<Record<string, PromptPair>>({});
  const [expandedStage, setExpandedStage] = useState<StageKey | null>("manager_plan");
  const [stageResults, setStageResults] = useState<Record<string, AgentStep>>({});
  const [stageOutputs, setStageOutputs] = useState<Record<string, string>>({});
  const [run, setRun] = useState<CouncilRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [runningStage, setRunningStage] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState<"preview" | "source" | "trace" | "research">("trace");
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    fetch(`${apiBaseUrl}/api/council/default-prompts`)
      .then((r) => r.json())
      .then((data: Record<string, PromptPair>) => {
        setDefaults(data);
        setPrompts({
          manager_plan: { ...data.manager_plan },
          seller_research: { ...data.seller_research },
          prospect_research: { ...data.prospect_research },
          manager_review: { ...data.manager_review },
          generate_microsite: { ...data.generate_microsite },
        });
      })
      .catch(() => {});
  }, []);

  function updatePrompt(stage: StageKey, key: "system" | "user", value: string) {
    setPrompts((prev) => ({ ...prev, [stage]: { ...prev[stage], [key]: value } }));
  }

  function resetStage(stage: StageKey) {
    if (defaults[stage]) {
      setPrompts((prev) => ({ ...prev, [stage]: { ...defaults[stage] } }));
    }
  }

  async function runSingleStage(stage: StageKey) {
    setRunningStage(stage);
    setError("");

    const context: Record<string, string> = {};
    if (stageOutputs.generation_plan) context.generation_plan = stageOutputs.generation_plan;
    if (stageOutputs.seller_research) context.seller_research = stageOutputs.seller_research;
    if (stageOutputs.prospect_research) context.prospect_research = stageOutputs.prospect_research;
    if (stageOutputs.review_notes) context.review_notes = stageOutputs.review_notes;

    try {
      const response = await fetch(`${apiBaseUrl}/api/council/stage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stage,
          prospect,
          source_company: sourceCompany,
          system_prompt: prompts[stage].system,
          user_prompt: prompts[stage].user,
          context,
        }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Stage failed (${response.status}): ${detail}`);
      }

      const stepResult: AgentStep = await response.json();
      setStageResults((prev) => ({ ...prev, [stage]: stepResult }));

      // Store output for downstream stages
      const outputMap: Record<string, string> = {
        manager_plan: "generation_plan",
        seller_research: "seller_research",
        prospect_research: "prospect_research",
        manager_review: "review_notes",
      };

      if (outputMap[stage] && stepResult.output) {
        setStageOutputs((prev) => ({ ...prev, [outputMap[stage]]: stepResult.output }));
      }

      // For generate_microsite, the output is HTML (but it's truncated in step.output)
      // We need the full output from the run for preview
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Stage failed");
    } finally {
      setRunningStage(null);
    }
  }

  async function runFullPipeline() {
    setLoading(true);
    setError("");
    setRun(null);
    setStageResults({});
    setStageOutputs({});

    try {
      const response = await fetch(`${apiBaseUrl}/api/council/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prospect,
          source_company: sourceCompany,
          stage_prompts: {
            manager_plan_system: prompts.manager_plan.system,
            manager_plan_user: prompts.manager_plan.user,
            seller_research_system: prompts.seller_research.system,
            seller_research_user: prompts.seller_research.user,
            prospect_research_system: prompts.prospect_research.system,
            prospect_research_user: prompts.prospect_research.user,
            manager_review_system: prompts.manager_review.system,
            manager_review_user: prompts.manager_review.user,
            generator_system: prompts.generate_microsite.system,
            generator_user: prompts.generate_microsite.user,
          },
        }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Pipeline failed (${response.status}): ${detail}`);
      }

      const data: CouncilRun = await response.json();
      setRun(data);

      // Populate stage outputs from the run
      setStageOutputs({
        generation_plan: data.generation_plan,
        seller_research: data.seller_research,
        prospect_research: data.prospect_research,
        review_notes: data.review_notes,
      });

      // Populate per-stage results
      const resultMap: Record<string, AgentStep> = {};
      for (const step of data.steps) {
        resultMap[step.step_name] = step;
      }
      setStageResults(resultMap);

      setViewMode(data.final_html ? "preview" : "trace");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Pipeline failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="pageShell">
      <nav className="topbar">
        <div className="brand">
          <div className="brandIcon">CA</div>
          <div className="brandBlock">
            <strong className="brandTitle">Council Sandbox</strong>
            <span className="brandCaption">Edit and test every agent prompt</span>
          </div>
        </div>
        <div className="navCluster">
          <Link className="navLink" href="/">Create</Link>
          <Link className="navLink" href="/microsites">Microsites</Link>
          <Link className="navLink" href="/observability">Observability</Link>
        </div>
      </nav>

      <section className="pageIntro">
        <div>
          <p className="kicker">Prompt engineering</p>
          <h1 className="pageTitle">Edit every agent prompt. Test each stage independently or run the full pipeline.</h1>
        </div>
      </section>

      {error ? <p className="errorText">{error}</p> : null}

      <section className="sandboxInputRow">
        <label className="fieldStack sandboxField">
          <div className="fieldTop">
            <strong>Source company (seller)</strong>
            <span className="fieldHint">Who is pitching</span>
          </div>
          <input className="prospectInput sandboxInput" value={sourceCompany} onChange={(e) => setSourceCompany(e.target.value)} />
        </label>
        <label className="fieldStack sandboxField">
          <div className="fieldTop">
            <strong>Prospect (target)</strong>
            <span className="fieldHint">Who is being pitched to</span>
          </div>
          <input className="prospectInput sandboxInput" value={prospect} onChange={(e) => setProspect(e.target.value)} />
        </label>
      </section>

      <section className="sandboxActions">
        <div className="actionRow">
          <button className="buttonPrimary" type="button" disabled={loading || !prospect.trim() || !sourceCompany.trim()} onClick={runFullPipeline}>
            {loading ? "Council running..." : "Run full pipeline"}
          </button>
          <button className="buttonTertiary" type="button" onClick={() => {
            if (defaults) setPrompts({
              manager_plan: { ...defaults.manager_plan },
              seller_research: { ...defaults.seller_research },
              prospect_research: { ...defaults.prospect_research },
              manager_review: { ...defaults.manager_review },
              generate_microsite: { ...defaults.generate_microsite },
            });
          }}>
            Reset all prompts
          </button>
        </div>
      </section>

      {loading ? (
        <section className="panel sandboxLoading">
          <div className="sandboxSpinner" />
          <div>
            <p className="kicker">Council executing</p>
            <h2 className="sectionTitle">5 agents running with your custom prompts. 30-90 seconds.</h2>
          </div>
        </section>
      ) : null}

      <section className="stageList">
        {STAGES.map((stage) => {
          const isExpanded = expandedStage === stage.key;
          const result = stageResults[stage.key];
          const isRunning = runningStage === stage.key;

          return (
            <article className={`panel stagePanel ${isExpanded ? "stageExpanded" : ""}`} key={stage.key}>
              <button className="stageHeader" type="button" onClick={() => setExpandedStage(isExpanded ? null : stage.key)}>
                <div className="stageHeaderLeft">
                  <strong>{stage.label}</strong>
                  <span className="stepAgentBadge">{stage.agent}</span>
                  {result ? (
                    <span className={`statusChip ${result.status === "completed" ? "statusReady" : "statusError"}`}>
                      {result.status} &middot; {result.duration_ms.toFixed(0)}ms
                      {result.cost_usd ? ` · $${result.cost_usd.toFixed(4)}` : ""}
                    </span>
                  ) : null}
                </div>
                <span className="stageChevron">{isExpanded ? "−" : "+"}</span>
              </button>

              {isExpanded ? (
                <div className="stageBody">
                  <div className="stagePromptGrid">
                    <div className="fieldStack">
                      <div className="fieldTop">
                        <strong>System prompt</strong>
                        <span className="fieldHint">Agent identity and instructions</span>
                      </div>
                      <textarea
                        className="sandboxTextarea stageTextarea"
                        value={prompts[stage.key].system}
                        onChange={(e) => updatePrompt(stage.key, "system", e.target.value)}
                      />
                    </div>
                    <div className="fieldStack">
                      <div className="fieldTop">
                        <strong>User prompt</strong>
                        <span className="fieldHint">{"{{prospect}}, {{source_company}}, {{generation_plan}}, etc."}</span>
                      </div>
                      <textarea
                        className="sandboxTextarea stageTextarea"
                        value={prompts[stage.key].user}
                        onChange={(e) => updatePrompt(stage.key, "user", e.target.value)}
                      />
                    </div>
                  </div>

                  <div className="actionRow">
                    <button
                      className="buttonSecondary"
                      type="button"
                      disabled={isRunning || loading}
                      onClick={() => runSingleStage(stage.key)}
                    >
                      {isRunning ? "Running..." : `Test ${stage.label}`}
                    </button>
                    <button className="buttonTertiary" type="button" onClick={() => resetStage(stage.key)}>
                      Reset to default
                    </button>
                  </div>

                  {result ? (
                    <div className="stageResult">
                      <div className="stepMetrics">
                        {result.model_name ? <span>Model: {result.model_name}</span> : null}
                        {result.input_tokens ? <span>In: {result.input_tokens}</span> : null}
                        {result.output_tokens ? <span>Out: {result.output_tokens}</span> : null}
                        {result.cost_usd ? <span>Cost: ${result.cost_usd.toFixed(4)}</span> : null}
                      </div>
                      <pre className="stepMeta">{result.output}</pre>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </article>
          );
        })}
      </section>

      {run && !loading ? (
        <section className="sandboxPreview">
          <div className="previewHeader">
            <div>
              <p className="kicker">{run.source_company} x {run.prospect} &middot; {run.status}</p>
              <h2 className="sectionTitle">Council run &middot; {(run.total_duration_ms / 1000).toFixed(1)}s &middot; ${run.total_cost_usd.toFixed(4)}</h2>
            </div>
            <div className="navCluster">
              {run.final_html ? <button className={`navLink ${viewMode === "preview" ? "active" : ""}`} type="button" onClick={() => setViewMode("preview")}>Preview</button> : null}
              <button className={`navLink ${viewMode === "research" ? "active" : ""}`} type="button" onClick={() => setViewMode("research")}>Research</button>
              <button className={`navLink ${viewMode === "trace" ? "active" : ""}`} type="button" onClick={() => setViewMode("trace")}>Trace</button>
              {run.final_html ? <button className={`navLink ${viewMode === "source" ? "active" : ""}`} type="button" onClick={() => setViewMode("source")}>Source</button> : null}
              {run.final_html ? (
                <button className="buttonTertiary" type="button" onClick={() => {
                  const blob = new Blob([run.final_html], { type: "text/html" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `${sourceCompany.toLowerCase()}-x-${prospect.toLowerCase()}.html`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}>
                  Download
                </button>
              ) : null}
            </div>
          </div>

          {viewMode === "preview" && run.final_html ? (
            <div className="frameShell sandboxFrame">
              <div className="frameBar">
                <div className="browserDots"><span /><span /><span /></div>
                <div className="frameAddress">{sourceCompany.toLowerCase()}-x-{prospect.toLowerCase()}.html</div>
                <div className="frameRoute">{run.status}</div>
              </div>
              <iframe ref={iframeRef} className="sandboxIframe" srcDoc={run.final_html} sandbox="allow-scripts allow-same-origin" title="Preview" />
            </div>
          ) : null}

          {viewMode === "research" ? (
            <div className="sandboxResearchGrid">
              <article className="panel detailPanel">
                <p className="kicker">Seller research</p>
                <div className="sandboxResearchContent">{run.seller_research.split("\n").map((l, i) => <p key={i}>{l || "\u00A0"}</p>)}</div>
              </article>
              <article className="panel detailPanel">
                <p className="kicker">Prospect research</p>
                <div className="sandboxResearchContent">{run.prospect_research.split("\n").map((l, i) => <p key={i}>{l || "\u00A0"}</p>)}</div>
              </article>
              <article className="panel detailPanel" style={{ gridColumn: "1 / -1" }}>
                <p className="kicker">Manager review</p>
                <div className="sandboxResearchContent">{run.review_notes.split("\n").map((l, i) => <p key={i}>{l || "\u00A0"}</p>)}</div>
              </article>
            </div>
          ) : null}

          {viewMode === "trace" ? (
            <div className="sandboxTrace">
              <div className="stepList">
                {run.steps.map((step, i) => (
                  <article className="stepItem" key={`${step.step_name}-${i}`}>
                    <div className="stepHead">
                      <div>
                        <strong>{step.step_name}</strong>
                        <span className="stepAgentBadge">{step.agent_role}</span>
                      </div>
                      <span>{step.duration_ms.toFixed(0)} ms</span>
                    </div>
                    <div className="stepMetrics">
                      {step.model_name ? <span>Model: {step.model_name}</span> : null}
                      {step.input_tokens ? <span>In: {step.input_tokens}</span> : null}
                      {step.output_tokens ? <span>Out: {step.output_tokens}</span> : null}
                      {step.cost_usd ? <span>Cost: ${step.cost_usd.toFixed(4)}</span> : null}
                      <span>Status: {step.status}</span>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {viewMode === "source" ? (
            <div className="panel sandboxSource">
              <pre className="sandboxCode">{run.final_html || "No HTML output."}</pre>
            </div>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
