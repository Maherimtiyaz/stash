import type { Save } from "../types";

/* Each category gets a bold flat colour, a text colour and a pattern, so saves are recognisable without thumbnails. */
type Look = { bg: string; fg: string; pattern: string };
const dots = (c: string) => `radial-gradient(${c} 1.6px, transparent 1.8px) 0 0 / 14px 14px`;
const stripes = (c: string) => `repeating-linear-gradient(135deg, ${c} 0 6px, transparent 6px 16px)`;
const grid = (c: string) => `linear-gradient(${c} 1px, transparent 1px) 0 0 / 18px 18px, linear-gradient(90deg, ${c} 1px, transparent 1px) 0 0 / 18px 18px`;
const checks = (c: string) => `conic-gradient(${c} 25%, transparent 0 50%, ${c} 0 75%, transparent 0) 0 0 / 22px 22px`;
const rings = (c: string) => `repeating-radial-gradient(circle at 80% 20%, ${c} 0 2px, transparent 2px 14px)`;
const waves = (c: string) => `radial-gradient(circle at 50% 100%, transparent 9px, ${c} 10px, ${c} 12px, transparent 13px) 0 0 / 24px 14px`;
const LOOKS: Record<string, Look> = {
  Travel: { bg: "#3d5afe", fg: "#ffffff", pattern: stripes("rgba(255,255,255,.12)") },
  Recipes: { bg: "#ff5a1f", fg: "#ffffff", pattern: dots("rgba(255,255,255,.28)") },
  Fitness: { bg: "#19c37d", fg: "#0d1f16", pattern: waves("rgba(0,0,0,.12)") },
  Fashion: { bg: "#ff6fb5", fg: "#2a0a1b", pattern: checks("rgba(255,255,255,.18)") },
  Tech: { bg: "#7b5cff", fg: "#ffffff", pattern: grid("rgba(255,255,255,.16)") },
  Health: { bg: "#b48cff", fg: "#1d0f3a", pattern: rings("rgba(255,255,255,.3)") },
  Home: { bg: "#ffc83d", fg: "#2a1a00", pattern: stripes("rgba(0,0,0,.07)") },
  Money: { bg: "#00b3a4", fg: "#ffffff", pattern: grid("rgba(255,255,255,.14)") },
  Books: { bg: "#c8823c", fg: "#ffffff", pattern: dots("rgba(255,255,255,.22)") },
  Unsorted: { bg: "#8f8a99", fg: "#ffffff", pattern: dots("rgba(255,255,255,.2)") },
};

/** Friendly shelf names. The backend keeps short names; people asked for "gym". */
const LABELS: Record<string, string> = { Fitness: "Gym & Fitness" };
export const shelfLabel = (category: string) => LABELS[category] ?? category;
const SPARE: Look[] = [
  { bg: "#ff3d6e", fg: "#ffffff", pattern: dots("rgba(255,255,255,.25)") },
  { bg: "#00a6ff", fg: "#ffffff", pattern: waves("rgba(255,255,255,.2)") },
  { bg: "#9be15d", fg: "#14240a", pattern: stripes("rgba(0,0,0,.08)") },
];

export function look(s: Pick<Save, "category" | "id">): Look {
  return LOOKS[s.category] ?? SPARE[s.id % SPARE.length];
}

/** Inline style for a card painted in a save's look. */
export function lookStyle(s: Pick<Save, "category" | "id">): Record<string, string> {
  const l = look(s);
  return { "--bg": l.bg, "--fg": l.fg, background: `${l.pattern}, ${l.bg}`, color: l.fg };
}

/** A small, stable tilt per save, so the wall feels hand-arranged. */
export function tilt(id: number): number {
  return (((id * 37) % 7) - 3) * 0.7;
}

export function title(s: Save): string {
  const t = s.caption.replace(/#\w+/g, "").trim();
  return t || (s.kind === "post" ? "Instagram post" : "Instagram reel");
}

export function ago(iso: string, now = new Date()): string {
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000);
  if (days < 1) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  if (days < 30) return `${Math.round(days / 7)} wk ago`;
  if (days < 360) return `${Math.round(days / 30)} mo ago`;
  const y = Math.round(days / 365);
  return y === 1 ? "1 year ago" : `${y} years ago`;
}

export function isoDate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function dayLabel(iso: string, todayIso = isoDate(new Date())): string {
  if (iso === todayIso) return "Today";
  const d = parseDay(iso);
  const t = parseDay(todayIso);
  if ((d.getTime() - t.getTime()) / 86_400_000 === 1) return "Tomorrow";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric" });
}

export function remindLabel(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

/** Quick reminder choices, computed in the viewer's local time and sent as UTC. */
export function reminderOptions(now = new Date()): { label: string; iso: string }[] {
  const at = (d: Date, h: number) => {
    const x = new Date(d);
    x.setHours(h, 0, 0, 0);
    return x;
  };
  const tonight = at(now, 20);
  const sat = at(addDays(now, ((6 - now.getDay() + 7) % 7) || 7), 10);
  const mon = at(addDays(now, ((1 - now.getDay() + 7) % 7) || 7), 9);
  const opts = [
    ...(tonight > now ? [{ label: "Tonight", d: tonight }] : [{ label: "Tomorrow", d: at(addDays(now, 1), 9) }]),
    { label: "Saturday", d: sat },
    { label: "Next week", d: mon },
  ];
  return opts.map((o) => ({ label: o.label, iso: o.d.toISOString() }));
}

/** Splits text into plain and matched parts for highlighting search words. */
export function highlight(text: string, words: string[]): { t: string; hit: boolean }[] {
  const ws = words.filter((w) => w.length > 1).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!ws.length) return [{ t: text, hit: false }];
  const re = new RegExp(`(${ws.join("|")})`, "ig");
  // split() with one capture group alternates: plain, match, plain, match…
  return text.split(re).map((t, i) => ({ t, hit: i % 2 === 1 })).filter((p) => p.t);
}

/** Free words in a query, without filters like in:"Goa trip" or is:todo. */
export function freeWords(q: string): string[] {
  return q.replace(/\b(in|by|is):("[^"]*"|\S+)/gi, " ").toLowerCase().split(/\s+/).filter(Boolean);
}
