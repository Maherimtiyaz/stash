import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Empty, Icon, Reel, Spinner, burst } from "../components/ui";
import { ago } from "../lib/format";
import { useApp } from "../store";
import type { ReviewAction, Save } from "../types";

const FLY: Record<ReviewAction, string> = {
  keep: "translate(130%, 30px) rotate(22deg)",
  let_go: "translate(-130%, 30px) rotate(-22deg)",
  later: "translate(0, -140%) rotate(-4deg)",
};
const MSG: Record<ReviewAction, string> = { keep: "Kept. It's on your to-try list", let_go: "Let it go", later: "Back on Saturday" };

/** Time capsule: forgotten saves, one at a time. Keep it, let it go, or bring it back later. */
export function RediscoverView() {
  const { toast, changed } = useApp();
  const [deck, setDeck] = useState<Save[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [tally, setTally] = useState({ keep: 0, let_go: 0, later: 0 });
  const [drag, setDrag] = useState({ x: 0, y: 0, active: false });
  const [leaving, setLeaving] = useState<ReviewAction | null>(null);
  const start = useRef({ x: 0, y: 0 });
  const keepBtn = useRef<HTMLButtonElement>(null);

  const load = () => api.rediscover().then((d) => (setDeck(d), setTotal(d.length))).catch((e: Error) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function act(action: ReviewAction) {
    const top = deck?.[0];
    if (!top || leaving) return;
    setLeaving(action);
    if (action === "keep") burst(keepBtn.current);
    try {
      await api.review(top.id, action);
      setTally((t) => ({ ...t, [action]: t[action] + 1 }));
      toast(MSG[action]);
      changed();
    } catch (e) {
      toast((e as Error).message);
      setLeaving(null);
      setDrag({ x: 0, y: 0, active: false });
      return;
    }
    window.setTimeout(() => {
      setDeck((d) => (d ? d.slice(1) : d));
      setLeaving(null);
      setDrag({ x: 0, y: 0, active: false });
    }, 260);
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input,textarea,[role=dialog]")) return;
      if (e.key === "ArrowRight") act("keep");
      if (e.key === "ArrowLeft") act("let_go");
      if (e.key === "ArrowUp") act("later");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const head = (
    <header className="page-head">
      <span className="kicker">Time capsule</span>
      <h1 className="mega small">Remember these?</h1>
      <p className="lede">Things you saved and forgot. Keep them, let them go, or have them come back on Saturday.</p>
    </header>
  );
  if (error) return <section className="view">{head}<p className="error">{error}</p></section>;
  if (!deck) return <section className="view">{head}<Spinner /></section>;
  if (!deck.length) {
    const any = tally.keep + tally.let_go + tally.later > 0;
    return (
      <section className="view">
        {head}
        <Empty art="🕰️" title={any ? "Capsule cleared!" : "Nothing forgotten right now"}>
          <p>{any ? `You kept ${tally.keep}, let go of ${tally.let_go} and snoozed ${tally.later}.` : "Saves you haven't touched in a while show up here."}</p>
          <button className="fat fat-ink" onClick={() => { setDeck(null); load(); }}>Check again</button>
        </Empty>
      </section>
    );
  }

  const done = total - deck.length;
  const yes = Math.max(0, drag.x / 90), no = Math.max(0, -drag.x / 90), up = Math.max(0, -drag.y / 90 - Math.abs(drag.x) / 120);
  const top = deck[0];
  const savedOn = new Date(top.saved_at).toLocaleDateString(undefined, { month: "short", year: "numeric" });

  return (
    <section className="view capsule">
      {head}
      <div className="capsule-progress" aria-label={`${done} of ${total} looked at`}>
        <span style={{ width: `${(done / total) * 100}%` }} />
        <b>{done + 1} / {total}</b>
      </div>
      <div className="deck">
        {deck.slice(0, 3).reverse().map((s) => {
          const k = deck.indexOf(s);
          const isTop = k === 0;
          const transform = isTop
            ? leaving ? FLY[leaving] : `translate(${drag.x}px, ${drag.y}px) rotate(${drag.x / 16}deg)`
            : `translate(${k * 10}px, ${k * 10}px) rotate(${k * 3}deg)`;
          return (
            <div key={s.id} className={`deck-card${isTop && drag.active ? " dragging" : ""}`} style={{ transform, zIndex: 3 - k }}
              onPointerDown={isTop ? (e) => { start.current = { x: e.clientX, y: e.clientY }; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); setDrag({ x: 0, y: 0, active: true }); } : undefined}
              onPointerMove={isTop ? (e) => drag.active && setDrag({ x: e.clientX - start.current.x, y: e.clientY - start.current.y, active: true }) : undefined}
              onPointerUp={isTop ? () => {
                if (drag.x > 90) act("keep");
                else if (drag.x < -90) act("let_go");
                else if (drag.y < -90) act("later");
                else setDrag({ x: 0, y: 0, active: false });
              } : undefined}
              aria-hidden={!isTop}>
              <Reel save={s} size="lg" still />
              {isTop && (
                <>
                  <span className="postmark" aria-hidden="true"><small>saved</small>{savedOn}</span>
                  <span className="verdict keep" style={{ opacity: leaving === "keep" ? 1 : yes }}>KEEP</span>
                  <span className="verdict go" style={{ opacity: leaving === "let_go" ? 1 : no }}>LET GO</span>
                  <span className="verdict later" style={{ opacity: leaving === "later" ? 1 : up }}>LATER</span>
                </>
              )}
            </div>
          );
        })}
      </div>
      <p className="capsule-age">You saved this <b>{ago(top.saved_at)}</b>{top.board_name ? <> · on “{top.board_name}”</> : null}</p>
      <div className="verdicts">
        <button className="fat fat-plain" onClick={() => act("let_go")}><Icon name="x" />Let go</button>
        <button className="fat fat-sun" onClick={() => act("later")}><Icon name="bell" />Later</button>
        <button ref={keepBtn} className="fat fat-mint" onClick={() => act("keep")}><Icon name="check" />Keep</button>
      </div>
      <p className="hint">Drag the card · or use ← ↑ → on a keyboard</p>
    </section>
  );
}
