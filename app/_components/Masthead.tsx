"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links: Array<{ href: string; label: string }> = [
  { href: "/", label: "Generate" },
  { href: "/microsites", label: "Library" },
  { href: "/observability", label: "Runs" },
  { href: "/prompts", label: "Prompts" },
];

export function Masthead() {
  const pathname = usePathname();
  return (
    <header className="masthead">
      <Link href="/" className="masthead__lockup">
        <span className="masthead__kicker">Microsite Studio — No. 01</span>
        <span className="masthead__title">
          The <em style={{ fontStyle: "italic", color: "var(--ember)" }}>Operator</em> Daily
        </span>
      </Link>
      <nav className="masthead__nav" aria-label="Primary">
        {links.map((link) => {
          const active =
            link.href === "/"
              ? pathname === "/"
              : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className="masthead__link"
              aria-current={active ? "page" : undefined}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
