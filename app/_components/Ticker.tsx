"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";

type Item = { label: string; value: string };

export function Ticker({ items, live = false }: { items: Item[]; live?: boolean }) {
  const dot = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!dot.current) return;
    if (!live) {
      gsap.set(dot.current, { opacity: 1, scale: 1 });
      return;
    }
    const tl = gsap.timeline({ repeat: -1, yoyo: true });
    tl.to(dot.current, { opacity: 0.25, scale: 0.7, duration: 0.9, ease: "sine.inOut" });
    return () => {
      tl.kill();
    };
  }, [live]);

  return (
    <div className="ticker" aria-live="polite">
      <span className="ticker__dot" ref={dot} aria-hidden />
      <div className="ticker__marquee">
        {items.map((it, i) => (
          <span key={i} style={{ color: "var(--ink)" }}>
            <strong>{it.label}</strong>&nbsp;{it.value}
            {i < items.length - 1 ? <span>·</span> : null}
          </span>
        ))}
      </div>
      <span style={{ color: live ? "var(--ember)" : "var(--ink-60)" }}>
        {live ? "Live" : "Idle"}
      </span>
    </div>
  );
}
