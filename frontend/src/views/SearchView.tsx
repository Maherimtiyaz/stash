import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { Empty, Icon, Reel, Spinner } from "../components/ui";
import { ago, freeWords, title } from "../lib/format";
import { useApp, useLoad } from "../store";

/** Home: your whole stash as a wall of reels. Type what you remember and the matches light up. */
export function SearchView() {
  const { me, boards, openSave, version } = useApp();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(q.trim()), 140);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && !(e.target as HTMLElement).closest("input,textarea")) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const home = useLoad(() => api.home(), []);
  const all = useLoad(() => api.search(""), []);
  const [hits, setHits] = useState<Set<number> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!debounced) return setHits(null);
    let live = true;
    api.search(debounced)
      .then((r) => live && (setHits(new Set(r.results.map((s) => s.id))), setError("")))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [debounced, version]);

  const saves = all.data?.results ?? null;
  const words = freeWords(debounced);
  const { matched, rest } = useMemo(() => {
    if (!saves) return { matched: [], rest: [] };
    if (!hits) return { matched: saves, rest: [] };
    return { matched: saves.filter((s) => hits.has(s.id)), rest: saves.filter((s) => !hits.has(s.id)) };
  }, [saves, hits]);

  const memory = [
    { label: "Never tried", q: "is:todo" },
    { label: "Already tried", q: "is:done" },
    ...boards.slice(0, 4).map((b) => ({ label: b.name, q: `in:"${b.name}"` })),
  ];
  const otd = home.data?.on_this_day[0];
  const c = home.data?.counts;
  const first = me.name.split(" ")[0];

  return (
    <section className="view home">
      <header className="home-head">
        <h1 className="mega">
          <span className="who">{first}’s</span> stash
        </h1>
        {c && (
          <div className="counts">
            <span className="count c1"><b>{c.total}</b> saved</span>
            <span className="count c2"><b>{c.done}</b> tried</span>
            <span className="count c3"><b>{c.todo}</b> waiting</span>
          </div>
        )}
      </header>

      <div className="search-dock">
        <form className="search" role="search" onSubmit={(e) => { e.preventDefault(); const first = matched[0]; if (hits && first) openSave(first.id); }}>
          <Icon name="search" size={22} />
          <input ref={input} id="q" type="search" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off"
            placeholder="What do you remember about it?" aria-label="Search your saves" />
          {q ? <button type="button" className="clear" onClick={() => setQ("")} aria-label="Clear">×</button> : <kbd>/</kbd>}
        </form>
        <div className="memory" aria-label="Quick filters">
          {memory.map((m) => {
            const on = q.includes(m.q);
            return (
              <button key={m.q} className={`mem${on ? " on" : ""}`} aria-pressed={on}
                onClick={() => setQ((cur) => (on ? cur.replace(m.q, "") : `${cur} ${m.q}`).replace(/\s+/g, " ").trim())}>
                {m.label}
              </button>
            );
          })}
        </div>
        {hits && (
          <p className="hits" role="status">
            {matched.length === 0 ? <>Nothing matches <b>“{debounced}”</b>. Try one word, a creator, or a #tag.</>
              : <><b>{matched.length}</b> {matched.length === 1 ? "save lights" : "saves light"} up · press Enter to open the first</>}
          </p>
        )}
      </div>

      {error && <p className="error">{error}</p>}
      {(all.error || home.error) && <p className="error">{all.error || home.error}</p>}
      {!saves && !all.error && <Spinner />}

      {saves && saves.length === 0 && (
        <Empty art="📮" title="Your stash is empty">
          <p>On Instagram, tap the paper plane on any reel and send it to <b>@stash</b>. It lands here in seconds.</p>
        </Empty>
      )}

      {saves && saves.length > 0 && (
        <div className="wall">
          {!hits && otd && (
            <div className="capsule-pin">
              <span className="tape">On this day · {ago(otd.saved_at)}</span>
              <Reel save={otd} onOpen={() => openSave(otd.id)} />
            </div>
          )}
          {matched.filter((s) => hits || s.id !== otd?.id).map((s) => (
            <Reel key={s.id} save={s} words={words} onOpen={() => openSave(s.id)} />
          ))}
          {rest.map((s) => <Reel key={s.id} save={s} dim onOpen={() => openSave(s.id)} />)}
        </div>
      )}

      {saves && saves.length > 0 && !hits && (
        <p className="foot-tip">Tip: search words from a caption, a creator like <code>by:@goadiaries</code>, a <code>#tag</code>, or anything you wrote in a note. {saves[0] && <>Latest: “{title(saves[0])}”.</>}</p>
      )}
    </section>
  );
}
