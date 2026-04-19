"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type MicrositeRecord = {
  id: string;
  company_name: string;
  slug: string;
  source_company_name: string;
  tagline: string;
  headline: string;
  summary: string;
  generated_at: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function MicrositesPage() {
  const [microsites, setMicrosites] = useState<MicrositeRecord[]>([]);
  const [selectedSlug, setSelectedSlug] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadMicrosites() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/microsites`);
        if (!response.ok) {
          throw new Error(`Unable to load microsites: ${response.status}`);
        }

        const data: MicrositeRecord[] = await response.json();
        setMicrosites(data);
        setSelectedSlug(data[0]?.slug ?? "");
      } catch (caughtError) {
        setError(caughtError instanceof Error ? caughtError.message : "Unable to load microsites");
      }
    }

    void loadMicrosites();
  }, []);

  const selectedMicrosite = useMemo(
    () => microsites.find((item) => item.slug === selectedSlug) ?? microsites[0] ?? null,
    [microsites, selectedSlug],
  );

  return (
    <main className="pageShell">
      <nav className="topbar">
        <div className="brand">
          <div className="brandIcon">LB</div>
          <div className="brandBlock">
            <strong className="brandTitle">Microsite Library</strong>
            <span className="brandCaption">Persisted route index</span>
          </div>
        </div>

        <div className="navCluster">
          <Link className="navLink" href="/">
            Create
          </Link>
          <Link className="navLink" href="/prompts">
            Prompt Library
          </Link>
          <Link className="navLink" href="/observability">
            Observability
          </Link>
        </div>
      </nav>

      <section className="pageIntro">
        <div>
          <p className="kicker">Generated assets</p>
          <h1 className="pageTitle">Browse the route library like a product inventory.</h1>
          <p className="sectionText">The library stays list-detail, fast to scan, and easy to reopen. Each microsite remains a persisted asset, not a temporary session artifact.</p>
        </div>

        <div className="metricGrid metricGridThree compactMetrics">
          <article className="metricCard">
            <span>Total microsites</span>
            <strong>{microsites.length}</strong>
          </article>
          <article className="metricCard">
            <span>Status</span>
            <strong>{microsites.length > 0 ? "Available" : "Waiting"}</strong>
          </article>
          <article className="metricCard">
            <span>Surface</span>
            <strong>List + detail</strong>
          </article>
        </div>
      </section>

      {error ? <p className="errorText">{error}</p> : null}

      <section className="libraryGrid">
        <aside className="panel selectorPanel">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Selector</p>
              <h2 className="sectionTitle">Stored microsites</h2>
            </div>
          </div>

          {microsites.length === 0 ? (
            <div className="emptyPanel">
              <p>No microsites generated yet.</p>
            </div>
          ) : (
            <div className="selectorList">
              {microsites.map((item) => (
                <button
                  key={item.id}
                  className={`selectorButton ${item.slug === selectedMicrosite?.slug ? "active" : ""}`}
                  onClick={() => setSelectedSlug(item.slug)}
                  type="button"
                >
                  <div className="selectorTop">
                    <span>{item.source_company_name}</span>
                    <strong>{new Date(item.generated_at).toLocaleDateString()}</strong>
                  </div>
                  <strong className="selectorTitle">{item.company_name}</strong>
                  <p>{item.slug}</p>
                </button>
              ))}
            </div>
          )}
        </aside>

        {!selectedMicrosite ? (
          <div className="emptyPanel">
            <p>Select a microsite when routes are available.</p>
          </div>
        ) : (
          <article className="panel previewPanel">
            <div className="previewHeader">
              <div>
                <p className="kicker">Selected route</p>
                <h2 className="sectionTitle">{selectedMicrosite.headline}</h2>
              </div>
              <div className="badgeRow">
                <span className="badge">{selectedMicrosite.source_company_name}</span>
                <span className="badge">{selectedMicrosite.company_name}</span>
                <span className="badge">/{selectedMicrosite.slug}</span>
              </div>
            </div>

            <div className="browserMock previewMock">
              <div className="browserBar">
                <div className="browserDots">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="browserAddress">/microsites/{selectedMicrosite.slug}</div>
                <div className="browserMeta">ready</div>
              </div>

              <div className="previewContent">
                <div className="previewHero">
                  <p className="miniLabel">{selectedMicrosite.tagline}</p>
                  <h3>{selectedMicrosite.headline}</h3>
                  <p>{selectedMicrosite.summary}</p>
                </div>

                <div className="previewStats">
                  <div className="previewStat">
                    <span>Route type</span>
                    <strong>Persisted detail page</strong>
                  </div>
                  <div className="previewStat">
                    <span>Generated</span>
                    <strong>{new Date(selectedMicrosite.generated_at).toLocaleString()}</strong>
                  </div>
                </div>
              </div>
            </div>

            <div className="actionRow">
              <Link className="buttonPrimary" href={`/microsites/${selectedMicrosite.slug}`}>
                Open microsite
              </Link>
              <Link className="buttonSecondary" href="/observability">
                Inspect generation trace
              </Link>
            </div>
          </article>
        )}
      </section>
    </main>
  );
}
