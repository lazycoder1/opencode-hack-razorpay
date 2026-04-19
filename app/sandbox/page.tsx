"use client";

import Link from "next/link";
import { useRef, useState } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const DEFAULT_SKILL = `You are a world-class frontend designer and developer. You create distinctive, production-grade HTML microsites with exceptional attention to aesthetic details and creative choices.

## Design Thinking

Before coding, commit to a BOLD aesthetic direction:
- Purpose: This is a first-touch sales microsite for an outbound campaign.
- Tone: Choose a clear visual direction that fits the brand pairing. Not generic, not templated.
- Differentiation: What makes this UNFORGETTABLE? One thing someone will remember.

## Output Format

Return ONLY a single, complete, self-contained HTML document. No markdown fences, no explanation, no preamble. Just the raw HTML starting with <!DOCTYPE html>.

The HTML must:
- Be a complete standalone page (inline all CSS, no external dependencies except Google Fonts)
- Include responsive design
- Use distinctive typography from Google Fonts (never Inter, Roboto, Arial)
- Have a cohesive color palette with CSS variables
- Include CSS animations for page load (staggered reveals, fade-ins)
- Feel like a real designer made it, not a template

## Frontend Aesthetics

- Typography: Choose beautiful, unique fonts. Pair a distinctive display font with a refined body font.
- Color: Commit to a cohesive palette. Dominant colors with sharp accents.
- Motion: CSS animations for load effects and micro-interactions. Staggered reveals create delight.
- Spatial composition: Unexpected layouts. Asymmetry. Generous negative space OR controlled density.
- Backgrounds: Create atmosphere with gradients, noise textures, geometric patterns, or grain overlays.

NEVER use generic AI aesthetics. No purple gradients on white. No predictable layouts. Each site should feel genuinely designed for the specific brand pairing.`;

const DEFAULT_PROMPT = `Create a sales microsite for a partnership pitch: {{source_company}} selling to {{company_name}}.

Context:
- {{source_company}} is the source company pitching their product.
- {{company_name}} is the prospect being pitched to.
- The microsite should pitch how {{source_company}}'s capabilities can power {{company_name}}'s growth.

The microsite should include:
1. A bold hero section with a compelling headline about the {{source_company}} x {{company_name}} opportunity
2. 3-4 key value propositions specific to what {{source_company}} can offer {{company_name}}
3. Relevant stats or proof points (can use general industry stats)
4. A clear CTA section
5. Footer with both brand marks referenced

Make it feel premium and modern. The design should reflect the speed and scale of both companies.

Remember: Return ONLY the raw HTML. No markdown, no code fences, no explanation.`;

type StepResult = {
  step_name: string;
  status: string;
  started_at: string;
  duration_ms: number;
  output: string;
  model_name: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  metadata: Record<string, unknown>;
};

type SandboxRun = {
  run_id: string;
  prospect: string;
  source_company: string;
  status: string;
  started_at: string;
  completed_at: string;
  total_duration_ms: number;
  steps: StepResult[];
  final_html: string;
};

export default function SandboxPage() {
  const [skill, setSkill] = useState(DEFAULT_SKILL);
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [prospect, setProspect] = useState("Zepto");
  const [sourceCompany, setSourceCompany] = useState("Razorpay");
  const [run, setRun] = useState<SandboxRun | null>(null);
  const [activeStep, setActiveStep] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState<"preview" | "source" | "trace">("preview");
  const iframeRef = useRef<HTMLIFrameElement>(null);

  async function runFullPipeline() {
    setLoading(true);
    setError("");
    setRun(null);
    setActiveStep("render_prompt");

    try {
      const response = await fetch(`${apiBaseUrl}/api/sandbox/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          system_prompt: skill,
          user_prompt: prompt,
          prospect,
          source_company: sourceCompany,
        }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Pipeline failed (${response.status}): ${detail}`);
      }

      const data: SandboxRun = await response.json();
      setRun(data);
      setActiveStep(null);
      setViewMode("preview");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Pipeline failed");
      setActiveStep(null);
    } finally {
      setLoading(false);
    }
  }

  async function runSingleStep(stepName: "render_prompt" | "generate") {
    setLoading(true);
    setError("");
    setActiveStep(stepName);

    try {
      let endpoint = "";
      let body: Record<string, string | null> = {};

      if (stepName === "render_prompt") {
        endpoint = "/api/sandbox/step/render-prompt";
        body = { system_prompt: skill, user_prompt: prompt, prospect, source_company: sourceCompany };
      } else {
        const renderedPrompt = prompt
          .replace(/\{\{company_name\}\}/g, prospect)
          .replace(/\{\{source_company\}\}/g, sourceCompany);
        endpoint = "/api/sandbox/step/generate";
        body = { system_prompt: skill, user_prompt: renderedPrompt };
      }

      const response = await fetch(`${apiBaseUrl}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Step failed (${response.status}): ${detail}`);
      }

      const stepResult: StepResult = await response.json();

      if (stepName === "generate") {
        let html = stepResult.output;
        if (html.includes("```html")) {
          html = html.replace(/```html\n?/g, "").replace(/```\n?/g, "");
        }

        setRun((prev) => {
          const steps = [...(prev?.steps ?? []), stepResult];
          return {
            run_id: prev?.run_id ?? "manual",
            prospect,
            source_company: sourceCompany,
            status: stepResult.status === "completed" ? "completed" : "failed",
            started_at: prev?.started_at ?? stepResult.started_at,
            completed_at: stepResult.started_at,
            total_duration_ms: steps.reduce((sum, s) => sum + s.duration_ms, 0),
            steps,
            final_html: html.trim(),
          };
        });
        setViewMode("preview");
      } else {
        setRun((prev) => {
          const steps = [stepResult, ...(prev?.steps.slice(1) ?? [])];
          return {
            run_id: prev?.run_id ?? "manual",
            prospect,
            source_company: sourceCompany,
            status: "partial",
            started_at: stepResult.started_at,
            completed_at: prev?.completed_at ?? "",
            total_duration_ms: steps.reduce((sum, s) => sum + s.duration_ms, 0),
            steps,
            final_html: prev?.final_html ?? "",
          };
        });
        setViewMode("trace");
      }
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Step failed");
    } finally {
      setActiveStep(null);
      setLoading(false);
    }
  }

  const genStep = run?.steps.find((s) => s.step_name === "generate_html");

  return (
    <main className="pageShell">
      <nav className="topbar">
        <div className="brand">
          <div className="brandIcon">SB</div>
          <div className="brandBlock">
            <strong className="brandTitle">Generation Sandbox</strong>
            <span className="brandCaption">Modular step runner</span>
          </div>
        </div>

        <div className="navCluster">
          <Link className="navLink" href="/">Create</Link>
          <Link className="navLink" href="/microsites">Microsites</Link>
          <Link className="navLink" href="/prompts">Prompts</Link>
          <Link className="navLink" href="/observability">Observability</Link>
        </div>
      </nav>

      <section className="pageIntro">
        <div>
          <p className="kicker">Prompt engineering</p>
          <h1 className="pageTitle">Run each pipeline step independently or execute the full flow.</h1>
          <p className="sectionText">
            Each step produces observability-compatible metadata. Run the full pipeline or trigger individual
            steps to iterate on the skill, prompt, or prospect targeting.
          </p>
        </div>
      </section>

      {error ? <p className="errorText">{error}</p> : null}

      <section className="sandboxInputRow">
        <label className="fieldStack sandboxField">
          <div className="fieldTop">
            <strong>Prospect</strong>
            <span className="fieldHint">Target company</span>
          </div>
          <input
            className="prospectInput sandboxInput"
            value={prospect}
            onChange={(e) => setProspect(e.target.value)}
            placeholder="Zepto"
          />
        </label>
        <label className="fieldStack sandboxField">
          <div className="fieldTop">
            <strong>Source company</strong>
            <span className="fieldHint">Your company</span>
          </div>
          <input
            className="prospectInput sandboxInput"
            value={sourceCompany}
            onChange={(e) => setSourceCompany(e.target.value)}
            placeholder="Razorpay"
          />
        </label>
      </section>

      <section className="sandboxGrid">
        <div className="panel sandboxEditor">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Step 1 &middot; System prompt</p>
              <h2 className="sectionTitle">Skill instructions</h2>
            </div>
            <span className="badge">Sent as system message</span>
          </div>
          <textarea
            className="sandboxTextarea"
            value={skill}
            onChange={(e) => setSkill(e.target.value)}
            placeholder="Skill/system prompt..."
          />
        </div>

        <div className="panel sandboxEditor">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Step 2 &middot; User prompt</p>
              <h2 className="sectionTitle">Generation template</h2>
            </div>
            <span className="badge">{"{{company_name}}"} and {"{{source_company}}"} get replaced</span>
          </div>
          <textarea
            className="sandboxTextarea sandboxTextareaShort"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="User prompt template..."
          />
        </div>
      </section>

      <section className="sandboxActions">
        <div className="actionRow">
          <button
            className="buttonPrimary"
            type="button"
            disabled={loading || !skill.trim() || !prompt.trim() || !prospect.trim()}
            onClick={runFullPipeline}
          >
            {loading && activeStep === "render_prompt" ? "Running pipeline..." : "Run full pipeline"}
          </button>

          <button
            className="buttonSecondary"
            type="button"
            disabled={loading || !prompt.trim() || !prospect.trim()}
            onClick={() => runSingleStep("render_prompt")}
          >
            {activeStep === "render_prompt" && loading ? "Rendering..." : "Step: Render prompt"}
          </button>

          <button
            className="buttonSecondary"
            type="button"
            disabled={loading || !skill.trim() || !prompt.trim() || !prospect.trim()}
            onClick={() => runSingleStep("generate")}
          >
            {activeStep === "generate" && loading ? "Generating..." : "Step: Generate HTML"}
          </button>

          <button
            className="buttonTertiary"
            type="button"
            onClick={() => {
              setSkill(DEFAULT_SKILL);
              setPrompt(DEFAULT_PROMPT);
              setProspect("Zepto");
              setSourceCompany("Razorpay");
            }}
          >
            Reset defaults
          </button>
        </div>
      </section>

      {loading ? (
        <section className="panel sandboxLoading">
          <div className="sandboxSpinner" />
          <div>
            <p className="kicker">
              {activeStep === "render_prompt" ? "Rendering prompt" : activeStep === "generate" ? "Generating HTML" : "Running pipeline"}
            </p>
            <h2 className="sectionTitle">
              {activeStep === "generate" || !activeStep
                ? "The LLM is writing a full HTML microsite. This takes 20-60 seconds."
                : "Rendering the prompt template with prospect variables."}
            </h2>
          </div>
        </section>
      ) : null}

      {run && !loading ? (
        <>
          <section className="sandboxPreview">
            <div className="previewHeader">
              <div>
                <p className="kicker">Run output &middot; {run.prospect}</p>
                <h2 className="sectionTitle">
                  {run.status === "completed" ? "Generated HTML microsite" : run.status === "partial" ? "Partial run" : "Run failed"}
                </h2>
              </div>
              <div className="navCluster">
                <button
                  className={`navLink ${viewMode === "preview" ? "active" : ""}`}
                  type="button"
                  onClick={() => setViewMode("preview")}
                >
                  Preview
                </button>
                <button
                  className={`navLink ${viewMode === "source" ? "active" : ""}`}
                  type="button"
                  onClick={() => setViewMode("source")}
                >
                  Source
                </button>
                <button
                  className={`navLink ${viewMode === "trace" ? "active" : ""}`}
                  type="button"
                  onClick={() => setViewMode("trace")}
                >
                  Trace
                </button>
                {run.final_html ? (
                  <button
                    className="buttonTertiary"
                    type="button"
                    onClick={() => {
                      const blob = new Blob([run.final_html], { type: "text/html" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `${sourceCompany.toLowerCase()}-x-${prospect.toLowerCase()}.html`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    Download HTML
                  </button>
                ) : null}
              </div>
            </div>

            {viewMode === "preview" && run.final_html ? (
              <div className="frameShell sandboxFrame">
                <div className="frameBar">
                  <div className="browserDots">
                    <span />
                    <span />
                    <span />
                  </div>
                  <div className="frameAddress">{sourceCompany.toLowerCase()}-x-{prospect.toLowerCase()}.html</div>
                  <div className="frameRoute">{run.status}</div>
                </div>
                <iframe
                  ref={iframeRef}
                  className="sandboxIframe"
                  srcDoc={run.final_html}
                  sandbox="allow-scripts allow-same-origin"
                  title="Generated microsite preview"
                />
              </div>
            ) : null}

            {viewMode === "preview" && !run.final_html ? (
              <div className="emptyPanel">
                <p>No HTML output yet. Run the generate step or the full pipeline.</p>
              </div>
            ) : null}

            {viewMode === "source" ? (
              <div className="panel sandboxSource">
                <pre className="sandboxCode">{run.final_html || "No HTML output yet."}</pre>
              </div>
            ) : null}

            {viewMode === "trace" ? (
              <div className="sandboxTrace">
                <div className="metricGrid metricGridFour compactMetrics">
                  <article className="metricCard">
                    <span>Run ID</span>
                    <strong>{run.run_id.slice(0, 8)}</strong>
                  </article>
                  <article className="metricCard">
                    <span>Status</span>
                    <strong>{run.status}</strong>
                  </article>
                  <article className="metricCard">
                    <span>Total duration</span>
                    <strong>{(run.total_duration_ms / 1000).toFixed(1)}s</strong>
                  </article>
                  <article className="metricCard">
                    <span>Steps</span>
                    <strong>{run.steps.length}</strong>
                  </article>
                </div>

                {genStep ? (
                  <div className="metricGrid metricGridFour compactMetrics">
                    <article className="metricCard">
                      <span>Model</span>
                      <strong>{genStep.model_name ?? "-"}</strong>
                    </article>
                    <article className="metricCard">
                      <span>LLM duration</span>
                      <strong>{(genStep.duration_ms / 1000).toFixed(1)}s</strong>
                    </article>
                    <article className="metricCard">
                      <span>Tokens in</span>
                      <strong>{genStep.input_tokens ?? "-"}</strong>
                    </article>
                    <article className="metricCard">
                      <span>Tokens out</span>
                      <strong>{genStep.output_tokens ?? "-"}</strong>
                    </article>
                  </div>
                ) : null}

                <div className="stepList">
                  {run.steps.map((step, index) => (
                    <article className="stepItem" key={`${step.step_name}-${index}`}>
                      <div className="stepHead">
                        <strong>{step.step_name}</strong>
                        <span>{step.duration_ms.toFixed(2)} ms</span>
                      </div>
                      <p className="stepStatus">{step.status}</p>
                      {Object.keys(step.metadata).length > 0 ? (
                        <pre className="stepMeta">{JSON.stringify(step.metadata, null, 2)}</pre>
                      ) : null}
                    </article>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
        </>
      ) : null}

      {!run && !loading ? (
        <section className="emptyPanel">
          <p>Configure the skill and prompt, then run the full pipeline or trigger individual steps.</p>
        </section>
      ) : null}
    </main>
  );
}
