"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { CSSProperties, useEffect, useMemo, useState } from "react";

type MicrositeRecord = {
  company_name: string;
  slug: string;
  tagline: string;
  headline: string;
  summary: string;
  cta_label: string;
  visual_direction: string;
  generated_at: string;
  generation_run_id: string | null;
  stats: string[];
  sections: Array<{
    title: string;
    body: string;
  }>;
  theme: {
    background: string;
    surface: string;
    accent: string;
    accent_soft: string;
    text: string;
    muted: string;
  };
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function hexToRgb(hex: string) {
  const normalized = hex.replace("#", "");
  const value = normalized.length === 3 ? normalized.split("").map((char) => `${char}${char}`).join("") : normalized;

  if (value.length !== 6) {
    return "240 180 106";
  }

  const number = Number.parseInt(value, 16);
  const red = (number >> 16) & 255;
  const green = (number >> 8) & 255;
  const blue = number & 255;
  return `${red} ${green} ${blue}`;
}

export default function MicrositeDetailPage() {
  const params = useParams<{ slug: string }>();
  const slug = Array.isArray(params.slug) ? params.slug[0] : params.slug;
  const [microsite, setMicrosite] = useState<MicrositeRecord | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadMicrosite() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/microsites/by-slug/${slug}`);
        if (!response.ok) {
          throw new Error(`Unable to load microsite: ${response.status}`);
        }

        const data: MicrositeRecord = await response.json();
        setMicrosite(data);
      } catch (caughtError) {
        setError(caughtError instanceof Error ? caughtError.message : "Unable to load microsite");
      }
    }

    if (slug) {
      void loadMicrosite();
    }
  }, [slug]);

  const themeStyle = useMemo(() => {
    if (!microsite) {
      return undefined;
    }

    return {
      "--microsite-bg": microsite.theme.background,
      "--microsite-surface": microsite.theme.surface,
      "--microsite-accent": microsite.theme.accent,
      "--microsite-soft": microsite.theme.accent_soft,
      "--microsite-text": microsite.theme.text,
      "--microsite-muted": microsite.theme.muted,
      "--microsite-accent-rgb": hexToRgb(microsite.theme.accent),
      "--microsite-soft-rgb": hexToRgb(microsite.theme.accent_soft),
    } as CSSProperties;
  }, [microsite]);

  if (error) {
    return (
      <main className="pageShell">
        <div className="emptyState">
          <p className="errorText">{error}</p>
          <Link className="buttonGhost" href="/microsites">
            Back to microsites
          </Link>
        </div>
      </main>
    );
  }

  if (!microsite) {
    return (
      <main className="pageShell">
        <div className="emptyState">
          <p>Loading microsite...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="posterPage" style={themeStyle}>
      <section className="posterHero">
        <div className="posterTopbar">
          <div className="brandMark">
            <div className="brandGlyph">/{microsite.slug.slice(0, 2).toUpperCase()}</div>
            <div className="brandCopy">
              <strong>{microsite.company_name}</strong>
              <span>Generated microsite route</span>
            </div>
          </div>
          <div className="posterActions">
            <Link className="buttonGhost" href="/microsites">
              Back to library
            </Link>
            {microsite.generation_run_id ? (
              <Link className="buttonSubtle" href="/observability">
                Trace run
              </Link>
            ) : null}
          </div>
        </div>

        <div className="posterGrid">
          <div>
            <p className="eyebrowCool">{microsite.tagline}</p>
            <h1 className="posterTitle">{microsite.headline}</h1>
            <p className="posterSummary">{microsite.summary}</p>

            <div className="posterStats">
              {microsite.stats.map((stat) => (
                <div className="posterStat" key={stat}>
                  <strong>{stat}</strong>
                </div>
              ))}
            </div>
          </div>

          <aside className="posterAside">
            <article className="posterAsideCard">
              <span>Visual direction</span>
              <strong>Design note</strong>
              <p>{microsite.visual_direction}</p>
            </article>
            <article className="posterAsideCard">
              <span>Generated at</span>
              <strong>{new Date(microsite.generated_at).toLocaleString()}</strong>
              <p>This route is persisted and can be reopened from the microsite library at any time.</p>
            </article>
            <article className="posterAsideCard">
              <span>Pipeline</span>
              <strong>{microsite.generation_run_id ? "Trace attached" : "No trace id"}</strong>
              <p>
                {microsite.generation_run_id
                  ? `Run id ${microsite.generation_run_id}`
                  : "This record was generated without a visible run identifier."}
              </p>
            </article>
          </aside>
        </div>
      </section>

      <section className="sectionGrid">
        {microsite.sections.map((section, index) => {
          const className =
            index % 3 === 0 ? "sectionCard wide" : index % 3 === 1 ? "sectionCard" : "sectionCard tight";

          return (
            <article className={className} key={section.title}>
              <p className="sectionLabel">Section {String(index + 1).padStart(2, "0")}</p>
              <h2 className="spotlightTitle">{section.title}</h2>
              <p>{section.body}</p>
            </article>
          );
        })}
      </section>

      <section className="ctaBand">
        <div>
          <p className="eyebrow">Ready for the next pass</p>
          <h2>Use this draft as the baseline, then enrich research, narrative, and operator traceability.</h2>
        </div>
        <button className="buttonPrimary" type="button">
          {microsite.cta_label}
        </button>
      </section>
    </main>
  );
}
