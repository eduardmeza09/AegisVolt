import { useId } from "react";

/** Cargador rápido con pantalla y contorno neón. `active` = conector entregando energía. */
export function Charger({ className, active = true }: { className?: string; active?: boolean }) {
  const id = useId().replace(/:/g, "");
  const neon = active ? "#36d6f5" : "#3b4652";
  return (
    <svg className={className} viewBox="0 0 230 380" role="img" aria-label="Cargador eléctrico">
      <defs>
        <filter id={`g-${id}`} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="7" />
        </filter>
        <linearGradient id={`body-${id}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#121820" />
          <stop offset="0.5" stopColor="#1d2631" />
          <stop offset="1" stopColor="#0b0f14" />
        </linearGradient>
        <linearGradient id={`screen-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#d6f8ff" />
          <stop offset="1" stopColor="#36d6f5" />
        </linearGradient>
      </defs>
      <ellipse cx="95" cy="356" rx="80" ry="10" fill={neon} opacity="0.35" filter={`url(#g-${id})`} />
      <rect x="32" y="20" width="126" height="320" rx="30" fill="none" stroke={neon} strokeWidth="6" filter={`url(#g-${id})`} />
      <rect x="32" y="20" width="126" height="320" rx="30" fill={`url(#body-${id})`} stroke={neon} strokeWidth="3" />
      <rect x="56" y="52" width="78" height="58" rx="9" fill={active ? `url(#screen-${id})` : "#1a222b"} />
      {active && <rect x="56" y="52" width="78" height="58" rx="9" fill="#36d6f5" opacity="0.6" filter={`url(#g-${id})`} />}
      <path d="M100 132 L86 158 H98 L92 180 L110 150 H98 L104 132 Z" fill={neon} />
      <circle cx="95" cy="230" r="26" fill="#0b0f14" stroke="#2a3542" strokeWidth="4" />
      <circle cx="95" cy="230" r="10" fill={neon} opacity="0.8" />
      <path d="M158 220 C200 222 214 262 206 300 C200 330 214 350 228 352" stroke="#0b0f14" strokeWidth="9" fill="none" strokeLinecap="round" />
      <path d="M158 220 C200 222 214 262 206 300 C200 330 214 350 228 352" stroke={neon} strokeOpacity="0.35" strokeWidth="2" fill="none" />
      <rect x="22" y="336" width="146" height="14" rx="7" fill="#0b0f14" stroke="#1f2833" />
    </svg>
  );
}
