"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type MicrositeRecord = {
  id: string;
  company_name: string;
  slug: string;
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
        <div className="brandMark">
          <div className="brandGlyph">MS</div>
          <div className="brandCopy">
            <strong>Microsite Library</strong>
            <span>Generated routes index</span>
          </div>
        </div>
        <div className="topbarNav">
          <Link href="/">Create</Link>
          <Link href="/observability">Observability</Link>
        </div>
      </nav>

      <section className="pageHeader">
        <div>
          <p className="eyebrow">Stored microsites</p>
          <h1 className="pageTitle">Browse the full account route board.</h1>
        </div>
        <div className="heroMeta">
          <div className="metaItem">
            <span>Total microsites</span>
            <strong>{microsites.length}</strong>
          </div>
          <div className="metaItem">
            <span>Status</span>
            <strong>{microsites.length === 0 ? "Waiting" : "Ready"}</strong>
          </div>
        </div>
      </section>

      {error ? <p className="errorText">{error}</p> : null}

      <section className="libraryLayout">
        <aside className="libraryRail">
          <div className="panelHeader">
            <p className="eyebrowCool">Selector</p>
            <p className="bodyText">Switch between generated accounts and open the final route from the spotlight.</p>
          </div>

          {microsites.length === 0 ? (
            <div className="emptyState">
              <p>No microsites have been generated yet.</p>
            </div>
          ) : (
            <div className="selectionList">
              {microsites.map((item) => (
                <button
                  key={item.id}
                  className={`libraryButton ${item.slug === selectedMicrosite?.slug ? "active" : ""}`}
                  onClick={() => setSelectedSlug(item.slug)}
                  type="button"
                >
                  <span>{item.tagline}</span>
                  <strong>{item.company_name}</strong>
                  <p>{item.slug}</p>
                </button>
              ))}
            </div>
          )}
        </aside>

        {!selectedMicrosite ? (
          <div className="emptyState">
            <p>Select a microsite once the library is populated.</p>
          </div>
        ) : (
          <article className="spotlightCard">
            <div className="spotlightMeta">
              <div>
                <p className="eyebrowCool">Spotlight route</p>
                <h2 className="spotlightTitle">{selectedMicrosite.headline}</h2>
              </div>
              <div className="miniPillRow">
                <div className="miniPill">
                  <span>Company</span>
                  <strong>{selectedMicrosite.company_name}</strong>
                </div>
                <div className="miniPill">
                  <span>Generated</span>
                  <strong>{new Date(selectedMicrosite.generated_at).toLocaleDateString()}</strong>
                </div>
              </div>
            </div>

            <p className="spotlightBody">{selectedMicrosite.summary}</p>

            <div className="metricsRow metricGrid">
              <article className="metricCard">
                <span>Route</span>
                <strong>/{selectedMicrosite.slug}</strong>
              </article>
              <article className="metricCard">
                <span>Mode</span>
                <strong>Generated</strong>
              </article>
              <article className="metricCard">
                <span>Surface</span>
                <strong>Microsite detail</strong>
              </article>
            </div>

            <div className="heroActions">
              <Link className="buttonPrimary" href={`/microsites/${selectedMicrosite.slug}`}>
                Open microsite page
              </Link>
              <Link className="buttonGhost" href="/observability">
                Inspect generation trace
              </Link>
            </div>
          </article>
        )}
      </section>
    </main>
  );
}
