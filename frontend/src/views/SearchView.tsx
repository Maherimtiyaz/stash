import { useEffect, useMemo, useRef, useState } from "react";
import { api, signOut } from "../api";
import { Empty, Icon, Reel, Spinner } from "../components/ui";
import { ago, freeWords, lookStyle, shelfLabel } from "../lib/format";
import { useApp, useLoad } from "../store";
import type { Save, Shelf } from "../types";

type Layout = "shelves" | "newest";
const LAYOUT_KEY = "stash_home_layout";
const readLayout = (): Layout => {
  try {
    return localStorage.getItem(LAYOUT_KEY) === "newest" ? "newest" : "shelves";
  } catch {
    return "shelves";
  }
};

interface Command { key: string; label: string; hint: string; run: () => void }

/** Home: one big search box (direction D), your saves sorted onto shelves (Tech, Travel, Recipes, Gym…). */
export function SearchView() {
  const { me, openSave, version, setRemindersOpen } = useApp();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [layout, setLayout] = useState<Layout>(readLayout);
  const [showRest, setShowRest] = useState(false);
  const [cmdIndex, setCmdIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(q.trim()), 140);
    return () => window.clearTimeout(t);
  }, [q]);
  useEffect(() => setShowRest(false), [debounced]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && !(e.target as HTMLElement).closest("input,textarea")) {
        e.preventDefault();
        setQ("/");
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const home = useLoad(() => api.home(), []);
  const all = useLoad(() => api.search(""), []);
  const shelvesRes = useLoad(() => api.shelves(), []);
  const [hits, setHits] = useState<Set<number> | null>(null);
  const [error, setError] = useState("");
  const isCommand = q.startsWith("/");
  useEffect(() => {
    if (!debounced || debounced.startsWith("/")) return setHits(null);
    let live = true;
    api.search(debounced)
      .then((r) => live && (setHits(new Set(r.results.map((s) => s.id))), setError("")))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [debounced, version]);

  const saves = all.data?.results ?? null;
  const shelves: Shelf[] = (shelvesRes.data ?? []).filter((s) => s.count > 0);
  const words = freeWords(debounced);
  const matched = useMemo(() => (saves && hits ? saves.filter((s) => hits.has(s.id)) : []), [saves, hits]);
  const rest = useMemo(() => (saves && hits ? saves.filter((s) => !hits.has(s.id)) : []), [saves, hits]);
  const byShelf = (list: Save[]) => {
    const order = (shelvesRes.data ?? []).map((s) => s.name);
    const groups = new Map<string, Save[]>();
    for (const s of list) groups.set(s.category, [...(groups.get(s.category) ?? []), s]);
    return [...groups.entries()].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
  };

  const filterFor = (name: string) => `in:${name}`;
  const toggle = (token: string) => setQ((cur) => (cur.includes(token) ? cur.replace(token, "") : `${cur.replace(/\bin:\S+/g, "")} ${token}`).replace(/\s+/g, " ").trim());
  const chooseLayout = (l: Layout) => {
    setLayout(l);
    try {
      localStorage.setItem(LAYOUT_KEY, l);
    } catch {
      /* not remembered */
    }
  };

  // Direction D's "/" commands.
  const go = (hash: string) => () => { setQ(""); window.location.hash = hash; };
  const commands: Command[] = [
    ...shelves.map((s) => ({ key: `/${shelfLabel(s.name).split(" ")[0].toLowerCase()}`, label: `Show ${shelfLabel(s.name)}`, hint: `${s.count} ${s.count === 1 ? "save" : "saves"}`, run: () => setQ(filterFor(s.name)) })),
    { key: "/todo", label: "Show what I haven't tried", hint: "is:todo", run: () => setQ("is:todo") },
    { key: "/done", label: "Show what I've tried", hint: "is:done", run: () => setQ("is:done") },
    { key: "/random", label: "Surprise me", hint: "open a random to-try save", run: () => {
      const pool = (saves ?? []).filter((s) => s.progress === "try");
      setQ("");
      if (pool.length) openSave(pool[Math.floor(Math.random() * pool.length)].id);
    } },
    { key: "/capsule", label: "Open the time capsule", hint: "forgotten saves", run: go("rediscover") },
    { key: "/piles", label: "Open your piles", hint: "boards", run: go("boards") },
    { key: "/plan", label: "Open this week's plan", hint: "plan", run: go("plan") },
    { key: "/reminders", label: "Set up reminders", hint: "DM, notifications, email", run: () => { setQ(""); setRemindersOpen(true); } },
    { key: "/signout", label: "Sign out", hint: "", run: () => { signOut().finally(() => window.location.replace(window.location.pathname)); } },
  ];
  const typed = q.slice(1).toLowerCase();
  const shown = commands.filter((c) => c.key.slice(1).startsWith(typed) || c.label.toLowerCase().includes(typed));
  useEffect(() => setCmdIndex(0), [q]);

  const c = home.data?.counts;
  const otd = home.data?.on_this_day[0];
  const first = me.name.split(" ")[0];

  return (
    <section className="view home">
      <header className="home-head">
        <h1 className="mega"><span className="who">{first}’s</span> stash</h1>
        {c && (
          <div className="counts">
            <span className="count c1"><b>{c.total}</b> saved</span>
            <span className="count c2"><b>{c.done}</b> tried</span>
            <span className="count c3"><b>{c.todo}</b> waiting</span>
          </div>
        )}
      </header>

      <div className="search-dock">
        <form className="search" role="search" onSubmit={(e) => {
          e.preventDefault();
          if (isCommand) return shown[cmdIndex]?.run();
          if (hits && matched[0]) openSave(matched[0].id);
        }}>
          <Icon name="search" size={22} />
          <input ref={input} id="q" type="search" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off"
            placeholder="What do you remember?" aria-label="Search your saves"
            aria-controls={isCommand ? "cmds" : undefined}
            onKeyDown={(e) => {
              if (!isCommand) return;
              if (e.key === "ArrowDown") { e.preventDefault(); setCmdIndex((i) => Math.min(i + 1, shown.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setCmdIndex((i) => Math.max(i - 1, 0)); }
              if (e.key === "Escape") setQ("");
            }} />
          {q ? <button type="button" className="clear" onClick={() => setQ("")} aria-label="Clear">×</button> : <kbd>/</kbd>}
        </form>

        {isCommand && (
          <div className="cmds" id="cmds" role="listbox" aria-label="Commands">
            {shown.length ? shown.map((cmd, i) => (
              <button key={cmd.key} role="option" aria-selected={i === cmdIndex} className="cmd" onMouseEnter={() => setCmdIndex(i)} onClick={cmd.run}>
                <code>{cmd.key}</code><span>{cmd.label}</span><small>{cmd.hint}</small>
              </button>
            )) : <p className="meta">No command like that. Try /tech, /todo or /random.</p>}
          </div>
        )}

        {!isCommand && shelves.length > 0 && (
          <div className="shelf-strip" aria-label="Shelves">
            {shelves.map((s) => {
              const token = filterFor(s.name);
              const on = q.includes(token);
              return (
                <button key={s.name} className={`shelf-chip${on ? " on" : ""}`} style={lookStyle({ category: s.name, id: 0 })} aria-pressed={on} onClick={() => toggle(token)}>
                  <b>{shelfLabel(s.name)}</b><span>{s.count}</span>
                </button>
              );
            })}
            {["is:todo", "is:done"].map((t) => (
              <button key={t} className={`mem${q.includes(t) ? " on" : ""}`} aria-pressed={q.includes(t)}
                onClick={() => setQ((cur) => (cur.includes(t) ? cur.replace(t, "") : `${cur} ${t}`).replace(/\s+/g, " ").trim())}>
                {t === "is:todo" ? "Never tried" : "Already tried"}
              </button>
            ))}
          </div>
        )}

        {!isCommand && hits && (
          <p className="hits" role="status">
            {matched.length === 0 ? <>Nothing matches <b>“{debounced}”</b>. Try one word, a creator, or a #tag.</>
              : <><b>{matched.length}</b> {matched.length === 1 ? "save" : "saves"} found · Enter opens the first</>}
          </p>
        )}
      </div>

      {(error || all.error || home.error) && <p className="error">{error || all.error || home.error}</p>}
      {!saves && !all.error && <Spinner />}

      {saves && saves.length === 0 && (
        <Empty art="📮" title="Your stash is empty">
          <p>On Instagram, tap the paper plane on any reel and send it to <b>@stash</b>. It lands on the right shelf in seconds.</p>
        </Empty>
      )}

      {/* Search results, grouped by shelf */}
      {saves && saves.length > 0 && hits && !isCommand && (
        <>
          {byShelf(matched).map(([cat, list]) => (
            <ShelfSection key={cat} name={cat} count={list.length}>
              <div className="wall">{list.map((s) => <Reel key={s.id} save={s} words={words} onOpen={() => openSave(s.id)} />)}</div>
            </ShelfSection>
          ))}
          {rest.length > 0 && (
            <div className="rest">
              <button className="pill ghost" onClick={() => setShowRest((v) => !v)}>
                {showRest ? "Hide" : "Show"} the other {rest.length} saves
              </button>
              {showRest && <div className="wall">{rest.map((s) => <Reel key={s.id} save={s} dim onOpen={() => openSave(s.id)} />)}</div>}
            </div>
          )}
        </>
      )}

      {/* Browsing: by shelf or newest */}
      {saves && saves.length > 0 && !hits && !isCommand && (
        <>
          <div className="layout-bar">
            <div className="seg" role="group" aria-label="Arrange saves">
              <button aria-pressed={layout === "shelves"} onClick={() => chooseLayout("shelves")}>By shelf</button>
              <button aria-pressed={layout === "newest"} onClick={() => chooseLayout("newest")}>Newest</button>
            </div>
            {otd && (
              <button className="otd-chip" onClick={() => openSave(otd.id)}>
                <span className="tape-mini">On this day</span> {ago(otd.saved_at)}: <b>{otd.caption.slice(0, 32)}{otd.caption.length > 32 ? "…" : ""}</b>
              </button>
            )}
          </div>

          {layout === "shelves" ? (
            byShelf(saves).map(([cat, list]) => (
              <ShelfSection key={cat} name={cat} count={list.length} todo={list.filter((s) => s.progress === "try").length}
                onSeeAll={list.length > 1 ? () => setQ(filterFor(cat)) : undefined}>
                <div className="shelf-row">{list.map((s) => <div key={s.id} className="shelf-item"><Reel save={s} onOpen={() => openSave(s.id)} /></div>)}</div>
              </ShelfSection>
            ))
          ) : (
            <div className="wall">{saves.map((s) => <Reel key={s.id} save={s} onOpen={() => openSave(s.id)} />)}</div>
          )}
        </>
      )}
    </section>
  );
}

function ShelfSection({ name, count, todo, onSeeAll, children }: { name: string; count: number; todo?: number; onSeeAll?: () => void; children: React.ReactNode }) {
  return (
    <section className="shelf" aria-label={shelfLabel(name)}>
      <header className="shelf-head">
        <span className="shelf-name" style={lookStyle({ category: name, id: 0 })}>{shelfLabel(name)}</span>
        <span className="shelf-count">{count} {count === 1 ? "save" : "saves"}{todo !== undefined && todo > 0 ? ` · ${todo} to try` : ""}</span>
        {onSeeAll && <button className="see-all" onClick={onSeeAll}>See all <Icon name="right" size={14} /></button>}
      </header>
      {children}
    </section>
  );
}
