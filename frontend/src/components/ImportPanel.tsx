import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { lookStyle, shelfLabel } from "../lib/format";
import { useApp, useLoad } from "../store";
import type { ImportSummary } from "../types";
import { Icon, burst } from "./ui";

/** Bring in years of old saves from Instagram's "Download your information" ZIP. */
export function ImportPanel() {
  const { importOpen, setImportOpen, changed, toast } = useApp();
  const history = useLoad(() => (importOpen ? api.imports() : Promise.resolve([])), [importOpen]);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ImportSummary | null>(null);
  const [confirmUndo, setConfirmUndo] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  const busyRef = useRef(false);
  busyRef.current = busy;

  // Fresh panel each time it opens. (Must not depend on `busy`, or finishing an upload would clear the result.)
  useEffect(() => {
    if (!importOpen) return;
    setError("");
    setResult(null);
    setConfirmUndo(null);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busyRef.current && setImportOpen(false);
    window.addEventListener("keydown", onKey);
    document.body.classList.add("locked");
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.classList.remove("locked");
    };
  }, [importOpen, setImportOpen]);

  if (!importOpen) return null;

  async function send(file: File | undefined) {
    if (!file || busy) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const r = await api.importExport(file);
      setResult(r);
      changed();
      history.reload();
      window.setTimeout(() => {
        resultRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        if (r.added) burst(resultRef.current);
      }, 50);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function undo(id: number) {
    try {
      const r = await api.undoImport(id);
      toast(`Undone: removed ${r.removed} saves${r.piles_removed ? ` and ${r.piles_removed} piles` : ""}`);
      setConfirmUndo(null);
      if (result?.id === id) setResult(null);
      changed();
      history.reload();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  const past = (history.data ?? []).filter((h) => h.id !== result?.id);

  return (
    <div className="viewer-wrap" onClick={(e) => e.target === e.currentTarget && !busy && setImportOpen(false)}>
      <div className="viewer import" role="dialog" aria-modal="true" aria-label="Import from Instagram">
        <button className="close" onClick={() => setImportOpen(false)} aria-label="Close" disabled={busy}><Icon name="x" /></button>
        <header className="page-head">
          <span className="kicker">Import</span>
          <h2 className="mega small">Bring in your old saves</h2>
          <p className="lede">Instagram can send you a file with everything you've ever saved. Stash reads it, sorts it onto shelves and turns your collections into piles.</p>
        </header>

        <ol className="steps">
          <li>In Instagram, open your profile → <b>☰</b> → <b>Accounts Center</b> → <b>Your information and permissions</b> → <b>Download your information</b>.</li>
          <li>Choose <b>Download or transfer information</b>, your account, then <b>Some of your information</b>, and tick only <b>Saved</b>.</li>
          <li>Pick <b>Download to device</b>, date range <b>All time</b>, format <b>JSON</b>, then <b>Create files</b>.</li>
          <li>Instagram emails you when it's ready (often minutes, sometimes a few hours). Download the ZIP.</li>
          <li>Drop it below. The menu names can differ slightly between app versions.</li>
        </ol>

        <label className={`dropzone${drag ? " over" : ""}${busy ? " busy" : ""}`} htmlFor="import-file"
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); send(e.dataTransfer.files[0]); }}>
          <input ref={input} id="import-file" type="file" accept=".zip,.json,.html,application/zip,application/json,text/html"
            onChange={(e) => send(e.target.files?.[0])} disabled={busy} />
          {busy ? (
            <><span className="spinner small" /><b>Reading your saves…</b></>
          ) : (
            <><span className="drop-icon" aria-hidden="true">⇪</span><b>Drop the ZIP here</b><span>or tap to choose it · ZIP, JSON or HTML</span></>
          )}
        </label>

        {error && <p className="notice" role="alert">{error}</p>}

        {result && (
          <div className="import-result" ref={resultRef} aria-live="polite">
            <h3>{result.added ? <>Added <b>{result.added.toLocaleString()}</b> saves</> : "Nothing new to add"}</h3>
            <ul className="facts-list">
              <li>{result.found.toLocaleString()} found in the file</li>
              {result.duplicates > 0 && <li>{result.duplicates.toLocaleString()} were already in your stash{result.put_on_piles ? ` (${result.put_on_piles} now on a pile)` : ""}</li>}
              {result.piles_created.length > 0 && <li>New piles from your collections: {result.piles_created.join(", ")}</li>}
            </ul>
            {Object.keys(result.shelves).length > 0 && (
              <div className="shelf-pick">
                {Object.entries(result.shelves).map(([name, n]) => (
                  <span key={name} className="shelf-dot on" style={lookStyle({ category: name, id: 0 })}>{shelfLabel(name)} · {n}</span>
                ))}
              </div>
            )}
            {(result.shelves.Unsorted ?? 0) > 0 && (
              <p className="meta">Instagram's file doesn't include captions, so some saves landed in Unsorted. Open one to move it to the right shelf.</p>
            )}
            <div className="row-actions">
              <button className="fat fat-ink" onClick={() => setImportOpen(false)}>See my stash</button>
              {result.added > 0 && (confirmUndo === result.id ? (
                <><span className="meta">Remove these {result.added} saves?</span>
                  <button className="pill danger-btn" onClick={() => undo(result.id)}>Undo import</button>
                  <button className="pill ghost" onClick={() => setConfirmUndo(null)}>Keep</button></>
              ) : <button className="pill ghost" onClick={() => setConfirmUndo(result.id)}>Undo this import</button>)}
            </div>
          </div>
        )}

        {past.length > 0 && (
          <section className="block">
            <h3>Earlier imports</h3>
            <ul className="upcoming">
              {past.map((h) => (
                <li key={h.id}>
                  <span className="meta">{new Date(h.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })} · {h.added} added</span>
                  {h.undone_at ? <span className="meta">undone</span> : confirmUndo === h.id ? (
                    <><button className="pill danger-btn" onClick={() => undo(h.id)}>Undo</button><button className="pill ghost" onClick={() => setConfirmUndo(null)}>Keep</button></>
                  ) : <button className="pill ghost" onClick={() => setConfirmUndo(h.id)}>Undo</button>}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
