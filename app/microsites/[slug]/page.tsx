"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { CSSProperties, useEffect, useMemo, useState } from "react";
import { BrandFlag } from "../../_components/BrandFlag";

type BrandKit = {
  fonts: {
    heading: string;
    body: string;
    google_url: string;
  };
  hero_image_path: string | null;
  favicon_path: string | null;
  wordmark_path: string | null;
};

type MicrositeRecord = {
  company_name: string;
  slug: string;
  source_company_id: string;
  source_company_name: string;
  source_company_website: string;
  source_company_logo_path: string;
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
  brand: BrandKit | null;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function hexToRgb(hex: string) {
  const normalized = hex.replace("#", "");
  const value = normalized.length === 3 ? normalized.split("").map((char) => `${char}${char}`).join("") : normalized;

  if (value.length !== 6) {
    return "114 84 217";
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

    const base: Record<string, string> = {
      "--artifact-bg": microsite.theme.background,
      "--artifact-surface": microsite.theme.surface,
      "--artifact-accent": microsite.theme.accent,
      "--artifact-soft": microsite.theme.accent_soft,
      "--artifact-text": microsite.theme.text,
      "--artifact-muted": microsite.theme.muted,
      "--artifact-accent-rgb": hexToRgb(microsite.theme.accent),
      "--artifact-soft-rgb": hexToRgb(microsite.theme.accent_soft),
    };

    if (microsite.brand?.fonts) {
      base["--brand-font-heading"] = `"${microsite.brand.fonts.heading}", var(--font-inter-tight), var(--font-ui)`;
      base["--brand-font-body"] = `"${microsite.brand.fonts.body}", var(--font-inter), var(--font-ui)`;
    }

    return base as CSSProperties;
  }, [microsite]);

  useEffect(() => {
    if (!microsite?.brand) return;
    const { favicon_path, fonts } = microsite.brand;

    const cleanups: Array<() => void> = [];

    if (favicon_path) {
      const existing = document.querySelector<HTMLLinkElement>('link[data-brand-favicon]');
      if (existing) existing.remove();
      const link = document.createElement("link");
      link.rel = "icon";
      link.type = favicon_path.endsWith(".svg") ? "image/svg+xml" : "image/png";
      link.href = favicon_path;
      link.setAttribute("data-brand-favicon", "true");
      document.head.appendChild(link);
      cleanups.push(() => link.remove());
    }

    if (fonts?.google_url) {
      const existing = document.querySelector<HTMLLinkElement>('link[data-brand-font]');
      if (existing) existing.remove();
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = fonts.google_url;
      link.setAttribute("data-brand-font", "true");
      document.head.appendChild(link);
      cleanups.push(() => link.remove());
    }

    return () => cleanups.forEach((fn) => fn());
  }, [microsite]);

  if (error) {
    return (
      <main className="pageShell">
        <div className="emptyPanel">
          <p className="errorText">{error}</p>
          <Link className="buttonSecondary" href="/microsites">
            Back to microsites
          </Link>
        </div>
      </main>
    );
  }

  if (!microsite) {
    return (
      <main className="pageShell">
        <div className="emptyPanel">
          <p>Loading microsite...</p>
        </div>
      </main>
    );
  }

  const branded = !!microsite.brand;

  const metaNotes = (
    <>
      <article className="artifactNote">
        <span>Visual direction</span>
        <strong>Design brief</strong>
        <p>{microsite.visual_direction || "A clean account-specific sales artifact with a strong first-touch narrative."}</p>
      </article>
      <article className="artifactNote">
        <span>Generated at</span>
        <strong>{new Date(microsite.generated_at).toLocaleString()}</strong>
        <p>This microsite is persisted and can be reopened from the main library at any time.</p>
      </article>
      <article className="artifactNote">
        <span>Traceability</span>
        <strong>{microsite.generation_run_id ? "Run linked" : "No run id"}</strong>
        <p>
          {microsite.generation_run_id
            ? `Observability run ${microsite.generation_run_id}`
            : "This record does not expose a generation run identifier."}
        </p>
      </article>
    </>
  );

  return (
    <main className={`detailShell${branded ? " brandedShell" : ""}`} style={themeStyle}>
      <nav className="topbar detailTopbar">
        <div className="brand">
          <img alt={microsite.source_company_name} className="brandLogo" src={microsite.source_company_logo_path} />
          <div className="brandBlock">
            <strong className="brandTitle">{microsite.company_name}</strong>
            <span className="brandCaption">Built with {microsite.source_company_name} context and brand inputs</span>
          </div>
        </div>

        <div className="navCluster">
          <Link className="navLink" href="/microsites">
            Library
          </Link>
          {microsite.generation_run_id ? (
            <Link className="navLink" href="/observability">
              View run
            </Link>
          ) : null}
        </div>
      </nav>

      <section className="frameShell">
        <div className="frameBar">
          <div className="browserDots">
            <span />
            <span />
            <span />
          </div>
          <div className="frameAddress">/microsites/{microsite.slug}</div>
          <div className="frameRoute">persisted</div>
        </div>

        <div className="artifactSurface">
          <section className="artifactHero">
            <div className="artifactCopy">
              <p className="artifactKicker">{microsite.tagline}</p>
              <h1 className="artifactTitle">{microsite.headline}</h1>
              <p className="artifactSummary">{microsite.summary}</p>
              <p className="statusNote">
                Source company: {microsite.source_company_name} · {microsite.source_company_website}
              </p>

              <div className="artifactStatRow">
                {microsite.stats.map((stat) => (
                  <div className="artifactStat" key={stat}>
                    <strong>{stat}</strong>
                  </div>
                ))}
              </div>
            </div>

            {branded && microsite.brand ? (
              <BrandFlag
                wordmarkSrc={microsite.brand.wordmark_path || microsite.source_company_logo_path}
                wordmark={microsite.source_company_name}
                accent={microsite.theme.accent}
                accentSoft={microsite.theme.accent_soft}
              />
            ) : (
              <aside className="artifactSidebar">{metaNotes}</aside>
            )}
          </section>

          {branded ? <div className="brandedMetaRow">{metaNotes}</div> : null}

          <section className="artifactGrid">
            {microsite.sections.map((section, index) => (
              <article className={`artifactSection ${index === 0 ? "artifactSectionWide" : ""}`} key={section.title}>
                <p className="artifactSectionLabel">Section {String(index + 1).padStart(2, "0")}</p>
                <h2>{section.title}</h2>
                <p>{section.body}</p>
              </article>
            ))}
          </section>

          <section className="artifactCta">
            <div>
              <p className="artifactSectionLabel">Next move</p>
              <h2>Use this as the reusable sales artifact, then enrich it with future research outputs.</h2>
            </div>

            <button className="artifactButton" type="button">
              {microsite.cta_label}
            </button>
          </section>
        </div>
      </section>
    </main>
  );
}
