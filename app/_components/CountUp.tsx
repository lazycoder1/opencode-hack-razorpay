"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";

type Props = {
  value: number;
  duration?: number;
  format?: (n: number) => string;
  className?: string;
};

export function CountUp({ value, duration = 0.7, format, className }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const prev = useRef(0);

  useEffect(() => {
    if (!ref.current) return;
    const obj = { n: prev.current };
    const tween = gsap.to(obj, {
      n: value,
      duration,
      ease: "power2.out",
      snap: { n: 1 },
      onUpdate: () => {
        if (ref.current) {
          ref.current.textContent = format ? format(obj.n) : String(obj.n);
        }
      },
    });
    prev.current = value;
    return () => {
      tween.kill();
    };
  }, [value, duration, format]);

  return (
    <span ref={ref} className={className}>
      {format ? format(0) : 0}
    </span>
  );
}
