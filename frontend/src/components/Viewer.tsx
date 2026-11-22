import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { addDays, ago, isoDate, parseDay, reminderOptions, remindLabel, title } from "../lib/format";
import { useApp } from "../store";
import type { Save, SaveChanges } from "../types";
import { Icon, Reel, Spinner, burst } from "./ui";

/** Opening a save: the reel large on one side, everything you can do with it on the other. */
export function Viewer() {
  const { openId, closeSave, boards, changed, toast, refreshBoards } = useApp();
  const [save, setSave] = useState<Save | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [newBoard, setNewBoard] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const triedBtn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setSave(null);
    setError("");
    setNewBoard(null);
    setConfirmDelete(false);
    if (openId == null) return;
    api.save(openId).then((s) => (setSave(s), setNote(s.note))).catch((e: Error) => setError(e.message));
  }, [openId]);

  useEffect(() => {
    if (openId == null) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeSave();
    window.addEventListener("keydown", onKey);
    panel.current?.focus({ preventScroll: true });
    panel.current?.parentElement?.scrollTo(0, 0);
    document.body.classList.add("locked");
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.classList.remove("locked");
    };
  }, [openId, closeSave]);

  if (openId == null) return null;

  async function apply(changes: SaveChanges, msg: string) {
    if (!save) return;
    const before = save;
    setSave({ ...save, ...changes });
    try {
      setSave(await api.update(save.id, changes));
      toast(msg);
      changed();
    } catch (e) {
      setSave(before);
      toast((e as Error).message);
    }
  }

  async function tried() {
    if (!save) return;
    if (save.progress === "done") return apply({ progress: "try" }, "Back on your to-try list");
    burst(triedBtn.current);
    await apply({ progress: "done" }, "Nice! Marked as tried");
  }

  async function createBoard() {
    if (!save || !newBoard?.trim()) return;
    try {
      const b = await api.createBoard(newBoard);
      await refreshBoards();
      setNewBoard(null);
      await apply({ board_id: b.id }, `New pile “${b.name}” made`);
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function remove() {
    if (!save) return;
    try {
      await api.remove(save.id);
      toast("Deleted from your stash");
      closeSave();
      changed();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  const today = new Date();
  const days = Array.from({ length: 7 }, (_, i) => isoDate(addDays(today, i)));

  return (
    <div className="viewer-wrap" onClick={(e) => e.target === e.currentTarget && closeSave()}>
      <div className="viewer" role="dialog" aria-modal="true" aria-label="Save" tabIndex={-1} ref={panel}>
        <button className="close" onClick={closeSave} aria-label="Close"><Icon name="x" /></button>
        {error && <p className="error">{error}</p>}
        {!save && !error && <Spinner />}
        {save && (
          <>
            <div className="viewer-reel">
              <Reel save={save} size="lg" still />
              {save.url && (
                <a className="watch" href={save.url} target="_blank" rel="noopener noreferrer"><Icon name="play" size={16} />Watch on Instagram</a>
              )}
            </div>

            <div className="viewer-body">
              <div className="viewer-head">
                <span className="kicker">{save.category} · saved {ago(save.saved_at)}</span>
                <h2>{title(save)}</h2>
                {save.creator && <span className="creator">{save.creator}</span>}
              </div>

              <div className="big-actions">
                <button ref={triedBtn} className={`fat fat-mint${save.progress === "done" ? " on" : ""}`} onClick={tried}>
                  <Icon name={save.progress === "done" ? "undo" : "check"} />{save.progress === "done" ? "Tried it · undo" : "I tried it"}
                </button>
                <button className={`fat fat-plain${save.progress === "skip" ? " on" : ""}`}
                  onClick={() => apply({ progress: save.progress === "skip" ? "try" : "skip" }, save.progress === "skip" ? "Back on your to-try list" : "Okay, skipped")}>
                  {save.progress === "skip" ? "Skipped · undo" : "Not for me"}
                </button>
              </div>

              <section className="block">
                <h3>When will you do it?</h3>
                <div className="tickets">
                  {days.map((d, i) => {
                    const on = save.plan_day === d;
                    const dt = parseDay(d);
                    return (
                      <button key={d} className={`ticket${on ? " on" : ""}`} aria-pressed={on}
                        onClick={() => apply({ plan_day: on ? null : d }, on ? "Taken off your plan" : `Planned for ${i === 0 ? "today" : i === 1 ? "tomorrow" : dt.toLocaleDateString(undefined, { weekday: "long" })}`)}>
                        <small>{i === 0 ? "Today" : dt.toLocaleDateString(undefined, { weekday: "short" })}</small>
                        <b>{dt.getDate()}</b>
                      </button>
                    );
                  })}
                </div>
                {save.plan_day && !days.includes(save.plan_day) && (
                  <p className="meta">Planned for {parseDay(save.plan_day).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short" })}</p>
                )}
              </section>

              <section className="block">
                <h3>Nudge me</h3>
                <div className="pills">
                  {reminderOptions().map((o) => (
                    <button key={o.label} className="pill" onClick={() => apply({ remind_at: o.iso }, `I'll nudge you ${remindLabel(o.iso)}`)}><Icon name="bell" size={14} />{o.label}</button>
                  ))}
                  {save.remind_at && <button className="pill ghost" onClick={() => apply({ remind_at: null }, "Nudge removed")}>Clear</button>}
                </div>
                {save.remind_at && <p className="meta">Nudge set for <b>{remindLabel(save.remind_at)}</b></p>}
              </section>

              <section className="block">
                <h3>Put it on a pile</h3>
                <div className="stickers">
                  {boards.map((b, i) => {
                    const on = save.board_id === b.id;
                    return (
                      <button key={b.id} className={`stk${on ? " on" : ""}`} style={{ ["--r" as string]: `${((i * 5) % 7) - 3}deg` }} aria-pressed={on}
                        onClick={() => apply({ board_id: on ? null : b.id }, on ? `Taken off “${b.name}”` : `Added to “${b.name}”`)}>
                        {b.name}
                      </button>
                    );
                  })}
                  {newBoard === null ? (
                    <button className="stk new" onClick={() => setNewBoard("")}><Icon name="plus" size={14} />New pile</button>
                  ) : (
                    <form className="new-pile" onSubmit={(e) => { e.preventDefault(); createBoard(); }}>
                      <input autoFocus aria-label="New pile name" placeholder="e.g. Goa trip" value={newBoard} maxLength={40} onChange={(e) => setNewBoard(e.target.value)} />
                      <button className="pill" type="submit" disabled={!newBoard.trim()}>Make it</button>
                      <button className="pill ghost" type="button" onClick={() => setNewBoard(null)}>Cancel</button>
                    </form>
                  )}
                </div>
              </section>

              <section className="block">
                <label className="note">
                  <span>Note to self</span>
                  <textarea id="note" value={note} onChange={(e) => setNote(e.target.value)}
                    onBlur={() => note !== save.note && apply({ note }, "Note saved")}
                    placeholder="Why did you save this? What would you change?" maxLength={2000} />
                </label>
              </section>

              {save.tags.length > 0 && <p className="meta tags">{save.tags.map((t) => `#${t}`).join("  ")}</p>}

              <div className="danger">
                {confirmDelete ? (
                  <>
                    <span>Delete this from your stash?</span>
                    <button className="pill danger-btn" onClick={remove}>Delete</button>
                    <button className="pill ghost" onClick={() => setConfirmDelete(false)}>Keep it</button>
                  </>
                ) : (
                  <button className="link" onClick={() => setConfirmDelete(true)}><Icon name="trash" size={14} />Delete from stash</button>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
