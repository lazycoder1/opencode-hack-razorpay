"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";

type MicrositeRecord = {
  id: string;
  company_name: string;
  slug: string;
  headline: string;
};

type GenerateResponse = {
  created: MicrositeRecord[];
  total_count: number;
  failed: string[];
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function Home() {
  const [prospects, setProspects] = useState(
    "Northstar Logistics\nAcme Capital\nJuniper Health\nBlue Atlas Energy",
  );
  const [created, setCreated] = useState<MicrositeRecord[]>([]);
  const [failed, setFailed] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const prospectList = useMemo(
    () =>
      prospects
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
    [prospects],
  );

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await fetch(`${apiBaseUrl}/api/microsites/generate-batch`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ prospects: prospectList }),
      });

      if (!response.ok) {
        throw new Error(`Generation failed with ${response.status}`);
      }

      const data: GenerateResponse = await response.json();
      setCreated(data.created);
      setFailed(data.failed);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to generate microsites");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="pageShell">
      <nav className="topbar">
        <div className="brandMark">
          <div className="brandGlyph">MS</div>
          <div className="brandCopy">
            <strong>Microsite Studio</strong>
            <span>Editorial outbound engine</span>
          </div>
        </div>
        <div className="topbarNav">
          <Link href="/microsites">Microsites</Link>
          <Link href="/observability">Observability</Link>
        </div>
      </nav>

      <section className="heroGrid">
        <article className="introPanel">
          <div className="introDeck">
            <div>
              <p className="eyebrowCool">Frontend redesign · signal-room edition</p>
              <h1 className="heroTitle">From raw prospect names to persuasive microsite drops.</h1>
              <p className="lede">
                This surface is the control room for the microsite track: queue a batch, trigger generation,
                inspect outcomes, then move directly into the generated routes and observability trail.
              </p>
            </div>

            <div className="introDeck">
              <div className="signalRow">
                <div className="signalPill">
                  <span>Input mode</span>
                  <strong>Manual list</strong>
                </div>
                <div className="signalPill">
                  <span>Pipeline</span>
                  <strong>OpenAI + LangGraph</strong>
                </div>
                <div className="signalPill">
                  <span>Output</span>
                  <strong>Unique microsite routes</strong>
                </div>
              </div>

              <div className="metricsRow metricGrid">
                <article className="metricCard">
                  <span>Queued prospects</span>
                  <strong>{prospectList.length}</strong>
                </article>
                <article className="metricCard">
                  <span>Created this session</span>
                  <strong>{created.length}</strong>
                </article>
                <article className="metricCard">
                  <span>Failed this session</span>
                  <strong>{failed.length}</strong>
                </article>
              </div>
            </div>
          </div>
        </article>

        <form className="composerPanel" onSubmit={handleGenerate}>
          <div className="panelHeader">
            <p className="eyebrow">Batch console</p>
            <p className="bodyText">
              One prospect per line. Keep it simple, then let the backend produce a first-pass microsite for
              every target in the list.
            </p>
          </div>

          <label className="fieldGroup" htmlFor="prospects">
            <div className="fieldLabel">
              <strong>Prospect roster</strong>
              <span className="fieldHint">{prospectList.length} rows ready</span>
            </div>
            <textarea
              id="prospects"
              value={prospects}
              onChange={(event) => setProspects(event.target.value)}
              placeholder="Northstar Logistics&#10;Acme Capital&#10;Juniper Health"
            />
          </label>

          <div className="heroActions">
            <div className="actionCluster">
              <button className="buttonPrimary" type="submit" disabled={loading || prospectList.length === 0}>
                {loading ? "Generating batch..." : "Generate microsites"}
              </button>
              <Link className="buttonGhost" href="/microsites">
                Open library
              </Link>
            </div>
            <Link className="buttonSubtle" href="/observability">
              View traces
            </Link>
          </div>

          <div className="statusBlock">
            <div className="statusPills">
              <div className={`statusPill ${loading ? "neutral" : "success"}`}>
                {loading ? "Generation in progress" : "Ready to run"}
              </div>
              {created.length > 0 ? <div className="statusPill success">Latest run produced routes</div> : null}
              {failed.length > 0 ? <div className="statusPill danger">Some prospects failed</div> : null}
            </div>

            {error ? <p className="errorText">{error}</p> : null}

            {failed.length > 0 ? (
              <div className="warningList">
                {failed.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </div>
            ) : null}
          </div>
        </form>
      </section>

      <section className="splitPanel">
        <article className="panel">
          <div className="panelHeader">
            <p className="eyebrow">Workflow</p>
            <h2 className="pageTitle">Four surfaces, one operating loop.</h2>
          </div>

          <div className="summaryGrid">
            <article className="summaryCard">
              <div>
                <p className="summaryLabel">01 · Queue</p>
                <h3>Manual prospect intake stays front and center.</h3>
              </div>
              <p>Use plain company names for now. This page remains the fastest route to a first demo batch.</p>
            </article>
            <article className="summaryCard">
              <div>
                <p className="summaryLabel">02 · Generate</p>
                <h3>Kick off a traced batch generation run.</h3>
              </div>
              <p>The backend writes structured microsites and run logs so the frontend reads persisted state only.</p>
            </article>
            <article className="summaryCard">
              <div>
                <p className="summaryLabel">03 · Browse</p>
                <h3>Review every generated microsite in one library.</h3>
              </div>
              <p>Open a route instantly, inspect the headline, and move from selector view into the rendered page.</p>
            </article>
            <article className="summaryCard">
              <div>
                <p className="summaryLabel">04 · Trace</p>
                <h3>Keep observability visible as part of the product.</h3>
              </div>
              <p>Operators can inspect timings, prompts, token counts, and request latency without touching raw JSON.</p>
            </article>
          </div>
        </article>

        <article className="panel resultsPanel">
          <div className="panelHeader">
            <p className="eyebrow">Latest session</p>
            <h2 className="pageTitle">Fresh routes from the current batch.</h2>
          </div>

          {created.length === 0 ? (
            <div className="emptyState">
              <p>No microsites generated in this session yet. Run a batch to populate the route board.</p>
            </div>
          ) : (
            <div className="summaryGrid">
              {created.map((item) => (
                <article className="summaryCard" key={item.id}>
                  <div>
                    <p className="summaryLabel">{item.company_name}</p>
                    <h3>{item.headline}</h3>
                  </div>
                  <div className="introStack">
                    <p className="summaryRoute">/{item.slug}</p>
                    <Link className="summaryAction" href={`/microsites/${item.slug}`}>
                      Open microsite
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          )}
        </article>
      </section>
    </main>
  );
}
