"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";

type Props = {
  children: React.ReactNode;
  delay?: number;
  stagger?: number;
  y?: number;
  className?: string;
  /** Target selector within children to stagger. If omitted, children direct children are animated. */
  targets?: string;
};

export function Reveal({
  children,
  delay = 0,
  stagger = 0.08,
  y = 24,
  className,
  targets,
}: Props) {
  const scope = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!scope.current) return;
    const ctx = gsap.context(() => {
      const items = targets
        ? gsap.utils.toArray<HTMLElement>(targets)
        : Array.from(scope.current!.children) as HTMLElement[];
      gsap.set(items, { opacity: 0, y });
      gsap.to(items, {
        opacity: 1,
        y: 0,
        delay,
        duration: 0.7,
        ease: "power3.out",
        stagger,
      });
    }, scope);
    return () => ctx.revert();
  }, [delay, stagger, y, targets]);

  return (
    <div ref={scope} className={className}>
      {children}
    </div>
  );
}
