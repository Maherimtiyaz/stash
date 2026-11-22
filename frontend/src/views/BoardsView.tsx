import { useState } from "react";
import { api } from "../api";
import { Empty, Icon, Reel, Spinner, Tile } from "../components/ui";
import { lookStyle } from "../lib/format";
import { useApp, useLoad } from "../store";
import type { Board, Save } from "../types";

type Open = number | "loose" | null;

/** Piles: each board is a little stack of reels. Open one to spread it out. */
export function BoardsView() {
  const { boards, openSave, toast, changed } = useApp();
  const [open, setOpen] = useState<Open>(null);
  const [mode, setMode] = useState<"none" | "new" | "rename" | "delete">("none");
  const [name, setName] = useState("");
  const all = useLoad(() => api.search(""), []);
  const saves = all.data?.results ?? null;

  async function submit() {
    try {
      if (mode === "new") {
        const b = await api.createBoard(name);
        toast(`New pile “${b.name}”`);
        setOpen(b.id);
      } else if (mode === "rename" && typeof open === "number") {
        await api.renameBoard(open, name);
        toast("Renamed");
      }
      setMode("none");
      setName("");
      changed();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function removeBoard(b: Board) {
    try {
      await api.deleteBoard(b.id);
      toast(`“${b.name}” is gone. Its saves are still in your stash.`);
      setOpen(null);
      setMode("none");
      changed();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  const nameForm = (mode === "new" || mode === "rename") && (
    <form className="pile-form" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <label htmlFor="pilename">{mode === "new" ? "Name your new pile" : "Rename this pile"}</label>
      <div className="row">
        <input id="pilename" autoFocus value={name} maxLength={40} onChange={(e) => setName(e.target.value)} placeholder="e.g. Goa trip, Sunday cooking" />
        <button className="fat fat-ink" type="submit" disabled={!name.trim()}>{mode === "new" ? "Make pile" : "Save"}</button>
        <button className="pill ghost" type="button" onClick={() => setMode("none")}>Cancel</button>
      </div>
    </form>
  );

  if (open !== null && saves) {
    const board = typeof open === "number" ? boards.find((b) => b.id === open) : undefined;
    const items = saves.filter((s) => (open === "loose" ? s.board_id == null : s.board_id === open));
    return (
      <section className="view">
        <button className="back" onClick={() => { setOpen(null); setMode("none"); }}><Icon name="left" size={18} />All piles</button>
        <header className="pile-head">
          <span className="board-cover" aria-hidden="true">
            {[0, 1, 2, 3].map((k) => <i key={k} style={items[k] ? lookStyle(items[k]) : undefined} />)}
          </span>
          <h1 className="mega small">{board ? board.name : "Not on a pile"}</h1>
          <span className="count c1"><b>{items.length}</b> saves</span>
          {board && mode === "none" && (
            <div className="pile-tools">
              <button className="pill" onClick={() => { setMode("rename"); setName(board.name); }}><Icon name="pencil" size={14} />Rename</button>
              <button className="pill" onClick={() => setMode("delete")}><Icon name="trash" size={14} />Delete</button>
            </div>
          )}
        </header>
        {nameForm}
        {board && mode === "delete" && (
          <div className="confirm">
            <span>Delete the pile “{board.name}”? The saves stay in your stash.</span>
            <button className="pill danger-btn" onClick={() => removeBoard(board)}>Delete pile</button>
            <button className="pill ghost" onClick={() => setMode("none")}>Keep it</button>
          </div>
        )}
        {items.length ? (
          <div className="moodboard">{items.map((s) => <Tile key={s.id} save={s} onOpen={() => openSave(s.id)} />)}</div>
        ) : (
          <Empty art="🫙" title="This pile is empty"><p>Open any save and tap this pile's name to add it.</p></Empty>
        )}
      </section>
    );
  }

  const loose = saves?.filter((s) => s.board_id == null) ?? [];
  const pile = (key: string, label: string, items: Save[], count: number, onClick: () => void, i: number) => (
    <button key={key} className="pile" onClick={onClick} style={{ ["--r" as string]: `${((i * 7) % 5) - 2}deg` }}>
      <span className="pile-stack">
        {items.slice(0, 3).map((s, k) => (
          <span key={s.id} className="pile-card" style={{ ["--k" as string]: k }}><Reel save={s} size="sm" still /></span>
        ))}
        {!items.length && <span className="pile-card ghost-card" />}
      </span>
      <span className="pile-label"><b>{label}</b><small>{count} {count === 1 ? "save" : "saves"}</small></span>
    </button>
  );

  return (
    <section className="view">
      <header className="page-head">
        <span className="kicker">Piles</span>
        <h1 className="mega small">Your piles</h1>
        <p className="lede">Group saves however your brain works: a trip, a project, a someday list.</p>
      </header>
      {nameForm}
      {all.error && <p className="error">{all.error}</p>}
      {!saves && !all.error && <Spinner />}
      {saves && (
        <div className="piles">
          {boards.map((b, i) => pile(String(b.id), b.name, saves.filter((s) => s.board_id === b.id), b.count, () => setOpen(b.id), i))}
          {loose.length > 0 && pile("loose", "Not on a pile", loose, loose.length, () => setOpen("loose"), boards.length)}
          <button className="pile new" onClick={() => { setMode("new"); setName(""); }}>
            <span className="pile-stack"><span className="pile-card ghost-card"><Icon name="plus" size={28} /></span></span>
            <span className="pile-label"><b>New pile</b><small>start one</small></span>
          </button>
        </div>
      )}
    </section>
  );
}
