import type { CSSProperties } from "react";

type Props = {
  wordmarkSrc: string;
  wordmark: string;
  accent: string;
  accentSoft: string;
};

export function BrandFlag({ wordmarkSrc, wordmark, accent, accentSoft }: Props) {
  const style: CSSProperties = {
    background: `linear-gradient(135deg, ${accentSoft} 0%, ${accent} 100%)`,
  };

  return (
    <div className="brandFlag" style={style} role="img" aria-label={`${wordmark} brand flag`}>
      <div className="brandFlagGlow" aria-hidden />
      <div className="brandFlagGrid" aria-hidden />
      <div className="brandFlagInner">
        <img className="brandFlagMark" src={wordmarkSrc} alt="" />
        <span className="brandFlagWordmark">{wordmark}</span>
        <span className="brandFlagTagline">Generated sales artifact</span>
      </div>
    </div>
  );
}
