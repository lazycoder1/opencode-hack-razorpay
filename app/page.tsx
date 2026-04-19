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
        <div className="brand">
          <div className="brandIcon">MS</div>
          <div className="brandBlock">
            <strong className="brandTitle">Microsite Studio</strong>
            <span className="brandCaption">Batch generation control plane</span>
          </div>
        </div>

        <div className="navCluster">
          <Link className="navLink" href="/microsites">
            Microsites
          </Link>
          <Link className="navLink" href="/prompts">
            Prompt Library
          </Link>
          <Link className="navLink" href="/observability">
            Observability
          </Link>
        </div>
      </nav>

      <section className="heroGrid">
        <article className="heroPanel">
          <p className="kicker">Operator workspace</p>
          <h1 className="heroTitle">Run batch microsite generation from one calm control surface.</h1>
          <p className="heroText">
            Queue prospects, trigger the generation pipeline, inspect provenance, and reopen every persisted
            route. The surface should feel like a serious internal product, not a marketing page.
          </p>

          <div className="badgeRow">
            <span className="badge">Manual intake</span>
            <span className="badge">Persisted microsites</span>
            <span className="badge">Run traceability</span>
          </div>

          <div className="metricGrid metricGridFour">
            <article className="metricCard">
              <span>Prospects queued</span>
              <strong>{prospectList.length}</strong>
            </article>
            <article className="metricCard">
              <span>Created now</span>
              <strong>{created.length}</strong>
            </article>
            <article className="metricCard">
              <span>Failed now</span>
              <strong>{failed.length}</strong>
            </article>
            <article className="metricCard">
              <span>Track</span>
              <strong>Microsite MVP</strong>
            </article>
          </div>
        </article>

        <article className="browserMock heroMock">
          <div className="browserBar">
            <div className="browserDots">
              <span />
              <span />
              <span />
            </div>
            <div className="browserAddress">studio://batch/generate</div>
            <div className="browserMeta">live</div>
          </div>

          <div className="browserContent">
            <div className="mockBlock">
              <p className="miniLabel">Current workflow</p>
              <div className="mockList">
                <div className="mockListItem active">
                  <strong>Queue prospects</strong>
                  <span>Paste one company per line</span>
                </div>
                <div className="mockListItem">
                  <strong>Run generation</strong>
                  <span>Create one persisted route per prospect</span>
                </div>
                <div className="mockListItem">
                  <strong>Inspect runs</strong>
                  <span>Timings, tokens, and request latency</span>
                </div>
              </div>
            </div>

            <div className="mockGrid">
              <div className="mockCard">
                <p className="miniLabel">Data contract</p>
                <strong>Slug, microsite output, generation run, API request log</strong>
              </div>
              <div className="mockCard">
                <p className="miniLabel">Delivery focus</p>
                <strong>Microsite track first. Research track stays separate.</strong>
              </div>
            </div>
          </div>
        </article>
      </section>

      <section className="mainGrid">
        <form className="panel formPanel" onSubmit={handleGenerate}>
          <div className="panelHeader">
            <div>
              <p className="kicker">Generate</p>
              <h2 className="sectionTitle">Paste a compact roster and run the batch.</h2>
            </div>
            <p className="sectionText">Today’s supported input is manual prospect entry. The UI stays explicit about that constraint.</p>
          </div>

          <label className="fieldStack" htmlFor="prospects">
            <div className="fieldTop">
              <strong>Prospect roster</strong>
              <span className="fieldHint">{prospectList.length} valid rows</span>
            </div>
            <textarea
              id="prospects"
              className="prospectInput"
              value={prospects}
              onChange={(event) => setProspects(event.target.value)}
              placeholder="Northstar Logistics&#10;Acme Capital&#10;Juniper Health&#10;Blue Atlas Energy"
            />
          </label>

          <div className="actionRow">
            <button className="buttonPrimary" type="submit" disabled={loading || prospectList.length === 0}>
              {loading ? "Generating microsites..." : "Generate microsites"}
            </button>
            <Link className="buttonSecondary" href="/microsites">
              Open microsite library
            </Link>
            <Link className="buttonTertiary" href="/observability">
              Inspect observability
            </Link>
          </div>

          <div className="statusRow">
            <span className={`statusChip ${loading ? "statusPending" : "statusReady"}`}>
              {loading ? "Generation in progress" : "Ready"}
            </span>
            {created.length > 0 ? <span className="statusChip statusReady">Routes created</span> : null}
            {failed.length > 0 ? <span className="statusChip statusError">Some prospects failed</span> : null}
          </div>

          {error ? <p className="errorText">{error}</p> : null}

          {failed.length > 0 ? (
            <div className="feedbackStack">
              {failed.map((item) => (
                <p className="errorText" key={item}>
                  {item}
                </p>
              ))}
            </div>
          ) : null}
        </form>

        <aside className="panel flowPanel">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Workflow</p>
              <h2 className="sectionTitle">One product loop, four visible surfaces.</h2>
            </div>
          </div>

          <div className="flowList">
            <article className="flowItem">
              <span className="flowIndex">01</span>
              <div>
                <strong>Enter prospects manually</strong>
                <p>Keep intake direct and avoid fake complexity before the demo needs it.</p>
              </div>
            </article>
            <article className="flowItem">
              <span className="flowIndex">02</span>
              <div>
                <strong>Generate persisted microsites</strong>
                <p>Each company gets a unique slug and a structured output that can be reopened later.</p>
              </div>
            </article>
            <article className="flowItem">
              <span className="flowIndex">03</span>
              <div>
                <strong>Inspect generation quality</strong>
                <p>Observability is part of the product surface, not a hidden admin afterthought.</p>
              </div>
            </article>
            <article className="flowItem">
              <span className="flowIndex">04</span>
              <div>
                <strong>Use the microsite as the artifact</strong>
                <p>Generated pages should feel credible, first-touch safe, and ready for later research enrichment.</p>
              </div>
            </article>
          </div>
        </aside>
      </section>

      <section className="panel resultsPanel">
        <div className="panelHeader">
          <div>
            <p className="kicker">Latest output</p>
            <h2 className="sectionTitle">Recent routes from this session.</h2>
          </div>
          <p className="sectionText">Successful outputs stay close to the operator so the next action is obvious.</p>
        </div>

        {created.length === 0 ? (
          <div className="emptyPanel">
            <p>No microsites generated in this session yet.</p>
          </div>
        ) : (
          <div className="resultGrid">
            {created.map((item) => (
              <article className="resultCard" key={item.id}>
                <p className="miniLabel">{item.company_name}</p>
                <h3>{item.headline}</h3>
                <p className="resultRoute">/{item.slug}</p>
                <Link className="textLink" href={`/microsites/${item.slug}`}>
                  Open microsite
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
