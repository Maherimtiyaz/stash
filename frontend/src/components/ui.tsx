import type { CSSProperties, ReactNode } from "react";
import { ago, highlight, lookStyle, parseDay, shelfLabel, tilt, title } from "../lib/format";
import type { Save } from "../types";

const PATHS = {
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  capsule: <><path d="M12 3a9 9 0 1 0 9 9" /><path d="M12 7v5l3 2" /><path d="M16 3h5v5" /></>,
  piles: <><rect x="4" y="7" width="13" height="14" rx="2" /><path d="M8 3h12v14" /></>,
  plan: <><rect x="3" y="4" width="18" height="17" rx="3" /><path d="M8 2v4M16 2v4M3 10h18" /></>,
  x: <path d="M18 6 6 18M6 6l12 12" />,
  check: <path d="M20 6 9 17l-5-5" />,
  bell: <><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" /></>,
  play: <path d="M7 4v16l13-8Z" />,
  ext: <path d="M14 3h7v7M10 14 21 3M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5" />,
  plus: <path d="M12 5v14M5 12h14" />,
  left: <path d="m15 18-6-6 6-6" />,
  right: <path d="m9 18 6-6-6-6" />,
  trash: <path d="M3 6h18M8 6V4h8v2M6 6l1 15h10l1-15" />,
  pencil: <path d="M17 3a2.8 2.8 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />,
  undo: <path d="M9 14 4 9l5-5M4 9h11a5 5 0 0 1 0 10h-3" />,
  sparkle: <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" />,
};
export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg className="i" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      {PATHS[name]}
    </svg>
  );
}

export function Hl({ text, words }: { text: string; words: string[] }) {
  return <>{highlight(text, words).map((p, i) => (p.hit ? <mark key={i}>{p.t}</mark> : <span key={i}>{p.t}</span>))}</>;
}

const weekday = (iso: string) => parseDay(iso).toLocaleDateString(undefined, { weekday: "short" });

/** A save drawn as a 9:16 reel cover: bold colour, pattern, big title, stickers and stamps. */
export function Reel({ save, words = [], onOpen, size = "md", dim = false, still = false, style, draggable, onDragStart }: {
  save: Save; words?: string[]; onOpen?: () => void; size?: "sm" | "md" | "lg"; dim?: boolean; still?: boolean;
  style?: CSSProperties; draggable?: boolean; onDragStart?: (e: React.DragEvent) => void;
}) {
  const t = still ? 0 : tilt(save.id);
  return (
    <button type="button" className={`reel reel-${size}${dim ? " dim" : ""}`} onClick={onOpen}
      style={{ ...lookStyle(save), ["--tilt" as string]: `${t}deg`, ...style }}
      draggable={draggable} onDragStart={onDragStart}
      aria-label={`${title(save)}${save.creator ? ` by ${save.creator}` : ""}, ${save.category}`}>
      <span className="reel-top">
        <span className="tag">{shelfLabel(save.category)}</span>
        <span className="reel-stickers">
          {save.plan_day && <span className="dot-sticker" title={`Planned for ${save.plan_day}`}>{weekday(save.plan_day)}</span>}
          {save.remind_at && <span className="dot-sticker bell" title="Reminder set"><Icon name="bell" size={12} /></span>}
        </span>
      </span>
      <span className="reel-play"><Icon name="play" size={size === "sm" ? 12 : 16} /></span>
      <span className="reel-title"><Hl text={title(save)} words={words} /></span>
      <span className="reel-by"><Hl text={save.creator || ago(save.saved_at)} words={words} /></span>
      {save.progress === "done" && <span className="stamp stamp-done">Tried it</span>}
      {save.progress === "skip" && <span className="stamp stamp-skip">Nope</span>}
    </button>
  );
}

const TILE_HEIGHTS = [190, 250, 210, 290, 230, 270];

/** A moodboard tile (direction B): free-height card for the Pinterest-style wall inside a pile. */
export function Tile({ save, onOpen }: { save: Save; onOpen?: () => void }) {
  return (
    <button type="button" className="tile" onClick={onOpen} style={{ ...lookStyle(save), height: TILE_HEIGHTS[save.id % TILE_HEIGHTS.length] }}
      aria-label={`${title(save)}${save.creator ? ` by ${save.creator}` : ""}`}>
      <span className="tag">{shelfLabel(save.category)}</span>
      {save.progress === "done" && <span className="stamp stamp-done">Tried it</span>}
      {save.progress === "skip" && <span className="stamp stamp-skip">Nope</span>}
      <b className="tile-title">{title(save)}</b>
      <small className="tile-by">{save.creator || ago(save.saved_at)}</small>
    </button>
  );
}

export function Empty({ art = "✦", title, children }: { art?: string; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty-art" aria-hidden="true">{art}</span>
      <h3>{title}</h3>
      {children}
    </div>
  );
}

export function Spinner() {
  return <div className="spinner" role="status" aria-label="Loading" />;
}

/** A short confetti burst from an element. Skipped when the person prefers reduced motion. */
export function burst(from: Element | null) {
  if (!from || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const r = from.getBoundingClientRect();
  const box = document.createElement("div");
  box.className = "confetti";
  box.style.left = `${r.left + r.width / 2}px`;
  box.style.top = `${r.top + r.height / 2}px`;
  const colours = ["#ff5a1f", "#ffc83d", "#19c37d", "#3d5afe", "#ff6fb5", "#7b5cff"];
  for (let i = 0; i < 28; i++) {
    const p = document.createElement("i");
    const a = (Math.PI * 2 * i) / 28 + Math.random() * 0.4;
    const d = 70 + Math.random() * 90;
    p.style.setProperty("--dx", `${Math.cos(a) * d}px`);
    p.style.setProperty("--dy", `${Math.sin(a) * d - 40}px`);
    p.style.setProperty("--r", `${Math.random() * 720 - 360}deg`);
    p.style.background = colours[i % colours.length];
    box.appendChild(p);
  }
  document.body.appendChild(box);
  window.setTimeout(() => box.remove(), 1000);
}
