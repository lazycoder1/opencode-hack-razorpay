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

The microsite should include:
1. A bold hero section with a compelling headline about the {{source_company}} x {{company_name}} opportunity
2. 3-4 key value propositions specific to what {{source_company}} can offer {{company_name}}
3. Relevant stats or proof points grounded in the research provided
4. A clear CTA section
5. Footer with both brand marks referenced

Make it feel premium and modern. The design should reflect the speed and scale of both companies.

Remember: Return ONLY the raw HTML. No markdown, no code fences, no explanation.`;

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

const AGENT_LABELS: Record<string, string> = {
  manager: "Manager",
  seller_researcher: "Seller Researcher",
  prospect_researcher: "Prospect Researcher",
  generator: "Microsite Generator",
};

const STEP_LABELS: Record<string, string> = {
  manager_plan: "Plan research",
  seller_research: "Research seller",
  prospect_research: "Research prospect",
  manager_review: "Review research",
  generate_microsite: "Generate HTML",
};

export default function SandboxPage() {
  const [skill, setSkill] = useState(DEFAULT_SKILL);
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [prospect, setProspect] = useState("Zepto");
  const [sourceCompany, setSourceCompany] = useState("Razorpay");
  const [run, setRun] = useState<CouncilRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState<"preview" | "source" | "trace" | "research">("trace");
  const iframeRef = useRef<HTMLIFrameElement>(null);

  async function runCouncil() {
    setLoading(true);
    setError("");
    setRun(null);

    try {
      const response = await fetch(`${apiBaseUrl}/api/council/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prospect,
          source_company: sourceCompany,
          skill_prompt: skill,
          user_prompt_template: prompt,
        }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Council run failed (${response.status}): ${detail}`);
      }

      const data: CouncilRun = await response.json();
      setRun(data);
      setViewMode(data.final_html ? "preview" : "trace");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Council run failed");
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
            <strong className="brandTitle">Council of Agents</strong>
            <span className="brandCaption">Manager + researchers + generator</span>
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
          <p className="kicker">Agent council</p>
          <h1 className="pageTitle">Manager plans, researchers investigate, generator builds.</h1>
          <p className="sectionText">
            The council runs 5 steps: Manager plans research, Seller Researcher and Prospect Researcher
            run in parallel, Manager reviews quality, then the Generator produces a full HTML microsite
            grounded in real research. Every step is traced with duration, tokens, and cost.
          </p>
        </div>
      </section>

      {error ? <p className="errorText">{error}</p> : null}

      <section className="sandboxInputRow">
        <label className="fieldStack sandboxField">
          <div className="fieldTop">
            <strong>Source company (seller)</strong>
            <span className="fieldHint">Who is pitching</span>
          </div>
          <input
            className="prospectInput sandboxInput"
            value={sourceCompany}
            onChange={(e) => setSourceCompany(e.target.value)}
            placeholder="Razorpay"
          />
        </label>
        <label className="fieldStack sandboxField">
          <div className="fieldTop">
            <strong>Prospect (target)</strong>
            <span className="fieldHint">Who is being pitched to</span>
          </div>
          <input
            className="prospectInput sandboxInput"
            value={prospect}
            onChange={(e) => setProspect(e.target.value)}
            placeholder="Zepto"
          />
        </label>
      </section>

      <section className="sandboxGrid">
        <div className="panel sandboxEditor">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Generator skill</p>
              <h2 className="sectionTitle">System prompt for the Generator agent</h2>
            </div>
            <span className="badge">Controls HTML output style</span>
          </div>
          <textarea
            className="sandboxTextarea"
            value={skill}
            onChange={(e) => setSkill(e.target.value)}
            placeholder="Skill/system prompt for the generator..."
          />
        </div>

        <div className="panel sandboxEditor">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Generator prompt template</p>
              <h2 className="sectionTitle">User prompt with research injected</h2>
            </div>
            <span className="badge">Research is appended automatically</span>
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
            disabled={loading || !skill.trim() || !prompt.trim() || !prospect.trim() || !sourceCompany.trim()}
            onClick={runCouncil}
          >
            {loading ? "Council running..." : "Run council pipeline"}
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
            <p className="kicker">Council executing</p>
            <h2 className="sectionTitle">
              5 agents running: plan, research seller, research prospect, review, generate. This takes 30-90 seconds.
            </h2>
            <p className="sectionText">
              The Manager plans, two Researchers run in parallel, the Manager reviews, then the Generator builds HTML from grounded research.
            </p>
          </div>
        </section>
      ) : null}

      {run && !loading ? (
        <section className="sandboxPreview">
          <div className="previewHeader">
            <div>
              <p className="kicker">{run.source_company} x {run.prospect} &middot; {run.status}</p>
              <h2 className="sectionTitle">Council run complete</h2>
            </div>
            <div className="navCluster">
              {run.final_html ? (
                <button className={`navLink ${viewMode === "preview" ? "active" : ""}`} type="button" onClick={() => setViewMode("preview")}>
                  Preview
                </button>
              ) : null}
              <button className={`navLink ${viewMode === "research" ? "active" : ""}`} type="button" onClick={() => setViewMode("research")}>
                Research
              </button>
              <button className={`navLink ${viewMode === "trace" ? "active" : ""}`} type="button" onClick={() => setViewMode("trace")}>
                Trace
              </button>
              {run.final_html ? (
                <button className={`navLink ${viewMode === "source" ? "active" : ""}`} type="button" onClick={() => setViewMode("source")}>
                  Source
                </button>
              ) : null}
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
                  Download
                </button>
              ) : null}
            </div>
          </div>

          <div className="metricGrid metricGridFour compactMetrics">
            <article className="metricCard">
              <span>Total duration</span>
              <strong>{(run.total_duration_ms / 1000).toFixed(1)}s</strong>
            </article>
            <article className="metricCard">
              <span>Total cost</span>
              <strong>${run.total_cost_usd.toFixed(4)}</strong>
            </article>
            <article className="metricCard">
              <span>Steps</span>
              <strong>{run.steps.length} agents</strong>
            </article>
            <article className="metricCard">
              <span>Status</span>
              <strong>{run.status}</strong>
            </article>
          </div>

          {viewMode === "preview" && run.final_html ? (
            <div className="frameShell sandboxFrame">
              <div className="frameBar">
                <div className="browserDots"><span /><span /><span /></div>
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

          {viewMode === "research" ? (
            <div className="sandboxResearchGrid">
              <article className="panel detailPanel">
                <div className="panelHeader compactHeader">
                  <div>
                    <p className="kicker">Seller research</p>
                    <h2 className="sectionTitle">{run.source_company}</h2>
                  </div>
                </div>
                <div className="sandboxResearchContent">
                  {run.seller_research.split("\n").map((line, i) => (
                    <p key={i}>{line || "\u00A0"}</p>
                  ))}
                </div>
              </article>

              <article className="panel detailPanel">
                <div className="panelHeader compactHeader">
                  <div>
                    <p className="kicker">Prospect research</p>
                    <h2 className="sectionTitle">{run.prospect}</h2>
                  </div>
                </div>
                <div className="sandboxResearchContent">
                  {run.prospect_research.split("\n").map((line, i) => (
                    <p key={i}>{line || "\u00A0"}</p>
                  ))}
                </div>
              </article>

              <article className="panel detailPanel" style={{ gridColumn: "1 / -1" }}>
                <div className="panelHeader compactHeader">
                  <div>
                    <p className="kicker">Manager review</p>
                    <h2 className="sectionTitle">Quality assessment</h2>
                  </div>
                </div>
                <div className="sandboxResearchContent">
                  {run.review_notes.split("\n").map((line, i) => (
                    <p key={i}>{line || "\u00A0"}</p>
                  ))}
                </div>
              </article>
            </div>
          ) : null}

          {viewMode === "trace" ? (
            <div className="sandboxTrace">
              <div className="stepList">
                {run.steps.map((step, index) => (
                  <article className="stepItem" key={`${step.step_name}-${index}`}>
                    <div className="stepHead">
                      <div>
                        <strong>{STEP_LABELS[step.step_name] ?? step.step_name}</strong>
                        <span className="stepAgentBadge">{AGENT_LABELS[step.agent_role] ?? step.agent_role}</span>
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
                    {Object.keys(step.metadata).length > 0 ? (
                      <pre className="stepMeta">{JSON.stringify(step.metadata, null, 2)}</pre>
                    ) : null}
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

      {!run && !loading ? (
        <section className="emptyPanel">
          <p>Configure the seller, prospect, skill, and prompt. Then run the full council pipeline.</p>
        </section>
      ) : null}
    </main>
  );
}
