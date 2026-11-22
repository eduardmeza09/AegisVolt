import { useId } from "react";

type Variant = "white" | "dark" | "blue";

const PAINT: Record<Variant, [string, string, string]> = {
  white: ["#f4f7fa", "#c9d2da", "#7d8a97"],
  dark: ["#2b323b", "#141920", "#06080b"],
  blue: ["#4d7dff", "#1f45d6", "#0b1f78"],
};

/** Auto eléctrico deportivo (perfil) con faros y luz inferior neón. */
export function Car({ variant = "white", glow = true, className }: { variant?: Variant; glow?: boolean; className?: string }) {
  const id = useId().replace(/:/g, "");
  const [c1, c2, c3] = PAINT[variant];
  const wheel = (cx: number) => (
    <g>
      <circle cx={cx} cy={180} r={39} fill="#07090c" stroke="#1d2530" strokeWidth={4} />
      <circle cx={cx} cy={180} r={26} fill={`url(#rim-${id})`} />
      {[0, 60, 120, 180, 240, 300].map((a) => (
        <rect key={a} x={cx - 2.5} y={156} width={5} height={24} rx={2} fill="#0d1116" transform={`rotate(${a} ${cx} 180)`} />
      ))}
      <circle cx={cx} cy={180} r={6} fill={glow ? "#36d6f5" : "#5b6672"} />
    </g>
  );
  return (
    <svg className={className} viewBox="0 0 650 240" role="img" aria-label="Vehículo eléctrico">
      <defs>
        <linearGradient id={`paint-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={c1} />
          <stop offset="0.55" stopColor={c2} />
          <stop offset="1" stopColor={c3} />
        </linearGradient>
        <linearGradient id={`glass-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#0d1620" />
          <stop offset="0.6" stopColor="#1c3242" />
          <stop offset="1" stopColor="#0a1118" />
        </linearGradient>
        <radialGradient id={`rim-${id}`}>
          <stop offset="0" stopColor="#c7d0d8" />
          <stop offset="1" stopColor="#4a5560" />
        </radialGradient>
        <filter id={`blur-${id}`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="9" />
        </filter>
        <filter id={`soft-${id}`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" />
        </filter>
      </defs>

      {glow && <ellipse cx="330" cy="214" rx="270" ry="13" fill="#22c3e6" opacity="0.55" filter={`url(#blur-${id})`} />}
      <ellipse cx="330" cy="218" rx="285" ry="9" fill="#000" opacity="0.6" />

      <path
        d="M40 170 L40 142 Q45 118 82 112 L184 103 C232 70 292 57 352 59 C414 61 452 86 484 104 L582 117 Q612 124 614 148
           L614 168 Q612 179 597 181 L526 181 A46 46 0 0 0 434 181 L206 181 A46 46 0 0 0 114 181 L54 181 Q40 179 40 170 Z"
        fill={`url(#paint-${id})`}
      />
      <path d="M90 142 C250 128 430 128 606 136" stroke="#fff" strokeOpacity="0.35" strokeWidth="2" fill="none" />
      <path d="M118 160 L210 160 M430 160 L520 160" stroke="#000" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M200 106 C242 78 292 70 346 70 L352 104 Z" fill={`url(#glass-${id})`} />
      <path d="M362 70 C406 72 436 90 460 104 L367 104 Z" fill={`url(#glass-${id})`} />
      <path d="M215 100 C250 82 290 76 330 75" stroke="#7fe6ff" strokeOpacity="0.25" strokeWidth="2" fill="none" />

      {/* faro delantero y piloto trasero */}
      {glow && <ellipse cx="600" cy="131" rx="26" ry="10" fill="#36d6f5" filter={`url(#blur-${id})`} />}
      <path d="M574 124 Q600 125 610 133 Q596 137 574 132 Z" fill={glow ? "#bff4ff" : "#e7eef4"} />
      {glow && <path d="M574 124 Q600 125 610 133 Q596 137 574 132 Z" fill="#36d6f5" filter={`url(#soft-${id})`} />}
      <rect x="42" y="124" width="22" height="6" rx="3" fill={glow ? "#36d6f5" : "#ff4d5e"} opacity="0.9" />

      {wheel(160)}
      {wheel(480)}
    </svg>
  );
}
