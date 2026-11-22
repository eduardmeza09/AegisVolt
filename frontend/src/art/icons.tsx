// Iconos de línea (24x24, stroke currentColor).
const base = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

export const Bolt = () => <svg {...base}><path d="M13 2 4 14h7l-1 8 9-12h-7z" /></svg>;
export const Plug = () => <svg {...base}><path d="M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0zM12 17v5" /></svg>;
export const Shield = () => <svg {...base}><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z" /><path d="m9 12 2 2 4-4" /></svg>;
export const Flag = () => <svg {...base}><path d="M5 21V4M5 4h11l-2 4 2 4H5" /></svg>;
export const History = () => <svg {...base}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></svg>;
export const Check = () => <svg {...base}><path d="m5 12 5 5 9-10" /></svg>;
export const Cross = () => <svg {...base}><path d="M6 6l12 12M18 6 6 18" /></svg>;
export const Undo = () => <svg {...base}><path d="M9 14 4 9l5-5" /><path d="M4 9h10a6 6 0 0 1 0 12h-3" /></svg>;
export const Dot = () => <svg {...base}><circle cx="12" cy="12" r="3" /></svg>;
export const Copy = () => <svg {...base}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg>;
export const Cpu = () => <svg {...base}><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" /></svg>;
export const Leaf = () => <svg {...base}><path d="M5 19c0-9 6-14 15-14 0 9-5 15-14 15" /><path d="M5 19 14 10" /></svg>;
export const Gauge = () => <svg {...base}><path d="M4 18a8 8 0 1 1 16 0" /><path d="m12 18 4-6" /></svg>;
export const Search = () => <svg {...base}><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></svg>;

export function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <circle cx="32" cy="32" r="27" fill="none" stroke="#22c3e6" strokeWidth="4" strokeDasharray="140 36"
        transform="rotate(-50 32 32)" />
      <path d="M35 11 20 36h11l-3 17 16-26H33z" fill="#22c3e6" />
    </svg>
  );
}
