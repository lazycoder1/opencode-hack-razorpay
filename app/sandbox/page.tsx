"use client";

import Link from "next/link";
import { FormEvent, useRef, useState } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const DEFAULT_SKILL = `You are a world-class frontend designer and developer. You create production-grade HTML microsites with a Linear-inspired browser-native aesthetic: calm, precise, dense enough to scan quickly, and polished without looking decorative.

## Design Direction

This is a first-touch sales microsite for an outbound campaign.

Use a design language inspired by Linear's public product surfaces:
- dark, neutral, low-noise UI chrome
- subtle layer separation instead of heavy gradients
- thin borders, compact spacing, and precise alignment
- restrained accent color used sparingly for focus and CTA moments
- clear browser/app-shell framing, as if the page lives inside a modern desktop workspace
- short, competent copy blocks instead of ad-like marketing fluff

## Output Format

Return ONLY a single, complete, self-contained HTML document. No markdown fences, no explanation, no preamble. Just the raw HTML starting with <!DOCTYPE html>.

The HTML must:
- Be a complete standalone page with inline CSS and JS only
- Include responsive design
- Feel like a premium product surface, not a launch page template
- Use a clean sans-serif stack appropriate for a serious software product
- Use CSS variables for the color system and spacing
- Include subtle motion only where it improves perceived quality

## Visual Rules

- Prefer graphite, slate, smoke, and soft blue-gray tones over bright colors
- Use panels, rails, pills, thin separators, and compact information clusters
- Make hierarchy obvious through spacing and contrast, not oversized type
- Use one accent color for CTA, active states, and focused highlights
- Keep shadows soft and shallow
- Keep radius values moderate, not bubbly

## Avoid

- loud gradients
- oversized hero marketing patterns
- glassmorphism
- neon accents
- playful copy
- ornamental illustrations
- chaotic layouts

The finished result should feel like a serious software workspace rendered as a microsite, with a browser-based Linear-adjacent aesthetic.`;

const DEFAULT_PROMPT = `Create a sales microsite for a partnership pitch: Razorpay selling to Zepto.

Context:
- Razorpay is India's leading full-stack payments company offering payment gateway, banking, lending, and insurance products.
- Zepto is a 10-minute grocery delivery startup in India, one of the fastest-growing quick commerce companies.
- The microsite should pitch how Razorpay's payment infrastructure can power Zepto's rapid growth.

The microsite should include:
1. A bold hero section with a compelling headline about the Razorpay x Zepto opportunity
2. 3-4 key value propositions (e.g., faster checkout, UPI autopay for subscriptions, payment success rate improvement, fraud protection for high-volume transactions)
3. Relevant stats or proof points (can use general industry stats about payments in quick commerce)
4. A clear CTA section
5. Footer with both brand marks referenced

Make it feel premium and modern. The design should reflect the speed and scale of both companies.

Remember: Return ONLY the raw HTML. No markdown, no code fences, no explanation.`;

type GenerateResult = {
  html: string;
  model_name: string;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  duration_ms: number;
};

export default function SandboxPage() {
  const [skill, setSkill] = useState(DEFAULT_SKILL);
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState<"preview" | "source">("preview");
  const iframeRef = useRef<HTMLIFrameElement>(null);

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(`${apiBaseUrl}/api/sandbox/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          system_prompt: skill,
          user_prompt: prompt,
        }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Generation failed (${response.status}): ${detail}`);
      }

      const data: GenerateResult = await response.json();

      let html = data.html;
      if (html.includes("```html")) {
        html = html.replace(/```html\n?/g, "").replace(/```\n?/g, "");
      }
      data.html = html.trim();

      setResult(data);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="pageShell">
      <nav className="topbar">
        <div className="brand">
          <div className="brandIcon">SB</div>
          <div className="brandBlock">
            <strong className="brandTitle">Generation Sandbox</strong>
            <span className="brandCaption">Prompt and frontend-skill experimentation</span>
          </div>
        </div>

        <div className="navCluster">
          <Link className="navLink" href="/">
            New batch
          </Link>
          <Link className="navLink" href="/prompts">
            Prompt library
          </Link>
        </div>
      </nav>

      <section className="pageIntro">
        <div>
          <p className="kicker">Prompt engineering</p>
          <h1 className="pageTitle">Nail the skill and prompt before wiring it into the pipeline.</h1>
          <p className="sectionText">
            Edit the system prompt (skill instructions) and user prompt independently. The LLM generates raw
            HTML directly instead of structured JSON rendered by a fixed React template.
          </p>
        </div>
      </section>

      {error ? <p className="errorText">{error}</p> : null}

      <form className="sandboxGrid" onSubmit={handleGenerate}>
        <section className="panel sandboxEditor">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">System prompt</p>
              <h2 className="sectionTitle">Skill instructions</h2>
            </div>
            <span className="badge">Sent as system message</span>
          </div>
          <textarea
            className="sandboxTextarea"
            value={skill}
            onChange={(event) => setSkill(event.target.value)}
            placeholder="The skill/system instructions that guide the LLM's design behavior..."
          />
        </section>

        <section className="panel sandboxEditor">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">User prompt</p>
              <h2 className="sectionTitle">Generation request</h2>
            </div>
            <span className="badge">Sent as user message</span>
          </div>
          <textarea
            className="sandboxTextarea sandboxTextareaShort"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="The specific generation request for this microsite..."
          />

          <div className="actionRow">
            <button className="buttonPrimary" type="submit" disabled={loading || !skill.trim() || !prompt.trim()}>
              {loading ? "Generating HTML..." : "Generate microsite"}
            </button>
            <button
              className="buttonTertiary"
              type="button"
              onClick={() => {
                setSkill(DEFAULT_SKILL);
                setPrompt(DEFAULT_PROMPT);
              }}
            >
              Reset defaults
            </button>
          </div>

          {result ? (
            <div className="sandboxMeta">
              <div className="metricGrid metricGridFour compactMetrics">
                <article className="metricCard">
                  <span>Model</span>
                  <strong>{result.model_name}</strong>
                </article>
                <article className="metricCard">
                  <span>Duration</span>
                  <strong>{(result.duration_ms / 1000).toFixed(1)}s</strong>
                </article>
                <article className="metricCard">
                  <span>Tokens in</span>
                  <strong>{result.input_tokens ?? "-"}</strong>
                </article>
                <article className="metricCard">
                  <span>Tokens out</span>
                  <strong>{result.output_tokens ?? "-"}</strong>
                </article>
              </div>
            </div>
          ) : null}
        </section>
      </form>

      {loading ? (
        <section className="panel sandboxLoading">
          <div className="sandboxSpinner" />
          <div>
            <p className="kicker">Generating</p>
            <h2 className="sectionTitle">The LLM is writing a full HTML microsite. This takes 20-60 seconds.</h2>
            <p className="sectionText">The system prompt (skill) and user prompt are being sent as a two-message conversation. The model returns a complete self-contained HTML document.</p>
          </div>
        </section>
      ) : null}

      {result && !loading ? (
        <section className="sandboxPreview">
          <div className="previewHeader">
            <div>
              <p className="kicker">Output</p>
              <h2 className="sectionTitle">Generated HTML microsite</h2>
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
                className="buttonTertiary"
                type="button"
                onClick={() => {
                  const blob = new Blob([result.html], { type: "text/html" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = "razorpay-x-zepto.html";
                  a.click();
                  URL.revokeObjectURL(url);
                }}
              >
                Download HTML
              </button>
            </div>
          </div>

          {viewMode === "preview" ? (
            <div className="frameShell sandboxFrame">
              <div className="frameBar">
                <div className="browserDots">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="frameAddress">razorpay-x-zepto.html</div>
                <div className="frameRoute">generated</div>
              </div>
              <iframe
                ref={iframeRef}
                className="sandboxIframe"
                srcDoc={result.html}
                sandbox="allow-scripts allow-same-origin"
                title="Generated microsite preview"
              />
            </div>
          ) : (
            <div className="panel sandboxSource">
              <pre className="sandboxCode">{result.html}</pre>
            </div>
          )}
        </section>
      ) : null}

      {!result && !loading ? (
        <section className="emptyPanel">
          <p>Edit the skill and prompt above, then hit Generate to see the raw HTML output rendered live.</p>
        </section>
      ) : null}
    </main>
  );
}
