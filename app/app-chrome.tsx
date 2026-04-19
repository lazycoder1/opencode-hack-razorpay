"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

const navItems = [
  { href: "/", label: "Create", meta: "Generate" },
  { href: "/microsites", label: "Microsites", meta: "Library" },
  { href: "/observability", label: "Observability", meta: "Runs" },
  { href: "/prompts", label: "Prompt Library", meta: "Prompts" },
  { href: "/sandbox", label: "Sandbox", meta: "Playground" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") {
    return pathname === "/";
  }

  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppChrome({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="appShell">
      <aside className="appSidebar">
        <div className="sidebarBrand">
          <div className="sidebarBrandMark">MS</div>
          <div>
            <p className="sidebarEyebrow">Workspace</p>
            <strong>Microsite Studio</strong>
          </div>
        </div>

        <nav className="sidebarNav" aria-label="Primary navigation">
          {navItems.map((item) => {
            const active = isActive(pathname, item.href);

            return (
              <Link className={`sidebarLink ${active ? "active" : ""}`} href={item.href} key={item.href}>
                <span>{item.label}</span>
                <small>{item.meta}</small>
              </Link>
            );
          })}
        </nav>

        <div className="sidebarFooter">
          <p className="sidebarEyebrow">Design mode</p>
          <strong>Light, precise, operator-first</strong>
          <p>Linear-inspired shell for generation, review, and prompt editing.</p>
        </div>
      </aside>

      <div className="appContent">{children}</div>
    </div>
  );
}
