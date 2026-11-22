import { useEffect, useState } from "react";
import { ApiError, api, setToken, takeToken } from "./api";
import { Viewer } from "./components/Viewer";
import { Empty, Icon, Spinner, type IconName } from "./components/ui";
import { AppProvider, useApp } from "./store";
import type { Me } from "./types";
import { RediscoverView } from "./views/RediscoverView";
import { SearchView } from "./views/SearchView";

type Tab = "search" | "rediscover" | "boards" | "plan";
const TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: "search", label: "Search", icon: "search" },
  { id: "rediscover", label: "Capsule", icon: "capsule" },
  { id: "boards", label: "Piles", icon: "piles" },
  { id: "plan", label: "Plan", icon: "plan" },
];
const fromHash = (): Tab => (TABS.find((t) => `#${t.id}` === window.location.hash)?.id ?? "search");

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [state, setState] = useState<"loading" | "signed-out" | "ready" | "error">("loading");
  const [error, setError] = useState("");

  const signIn = () => {
    if (!takeToken()) return setState("signed-out");
    setState("loading");
    api.me()
      .then((m) => (setMe(m), setState("ready")))
      .catch((e: Error) => {
        if (e instanceof ApiError && e.status === 401) {
          setToken(null);
          setState("signed-out");
        } else {
          setError(e.message);
          setState("error");
        }
      });
  };
  useEffect(signIn, []);

  if (state === "loading") return <div className="center"><Spinner /></div>;
  if (state === "error") return <div className="center"><p className="error">{error}</p><button className="btn" onClick={signIn}>Try again</button></div>;
  if (state === "signed-out" || !me) return <SignIn onDone={signIn} />;
  return (
    <AppProvider me={me}>
      <Shell />
    </AppProvider>
  );
}

function Shell() {
  const { toastMsg, closeSave } = useApp();
  const [tab, setTab] = useState<Tab>(fromHash);
  useEffect(() => {
    const on = () => setTab(fromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = (t: Tab) => {
    closeSave();
    window.location.hash = t;
    setTab(t);
    window.scrollTo(0, 0);
  };

  return (
    <div className="shell">
      <header className="topbar">
        <span className="wordmark">stash<i>✦</i></span>
        <button className="signout" onClick={() => { setToken(null); window.location.reload(); }}>Sign out</button>
      </header>
      <main className="main" id="main">
        {tab === "search" && <SearchView />}
        {tab === "rediscover" && <RediscoverView />}
        {tab === "boards" && <Soon name="boards" />}
        {tab === "plan" && <Soon name="plan" />}
      </main>
      <nav className="dock" aria-label="Sections">
        {TABS.map((t) => (
          <button key={t.id} className="dock-btn" aria-current={tab === t.id ? "page" : undefined} onClick={() => go(t.id)}>
            <Icon name={t.icon} size={22} /><span>{t.label}</span>
          </button>
        ))}
      </nav>
      <Viewer />
      {toastMsg && <div className="toast" role="status" key={toastMsg}>{toastMsg}</div>}
    </div>
  );
}

function SignIn({ onDone }: { onDone: () => void }) {
  const [link, setLink] = useState("");
  const [err, setErr] = useState("");
  const submit = () => {
    const m = link.match(/[?&]t=([^&#\s]+)/) ?? link.trim().match(/^(\d+\.[a-f0-9]{16,})$/);
    if (!m) return setErr("That doesn't look like a Stash link. It contains ?t= followed by a code.");
    setToken(decodeURIComponent(m[1]));
    onDone();
  };
  return (
    <div className="signin">
      <div className="signin-card">
        <span className="wordmark big">stash<i>✦</i></span>
        <h1>Your saves,<br />finally findable.</h1>
        <p>Stash signs you in with the private link <b>@stash</b> sent you on Instagram. Tap that link, or send <code>LIBRARY</code> to @stash for a fresh one.</p>
        <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <label htmlFor="link">Or paste your link</label>
          <input id="link" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://…/app/?t=…" autoComplete="off" />
          {err && <p className="error">{err}</p>}
          <button className="fat fat-ink" type="submit" disabled={!link.trim()}>Open my stash</button>
        </form>
        <p className="meta">No account? Stash is invite-only. Ask whoever told you about it for an invite.</p>
      </div>
      <div className="signin-art" aria-hidden="true">
        {["#ff5a1f", "#3d5afe", "#ffc83d", "#ff6fb5", "#19c37d"].map((c, i) => <span key={c} style={{ background: c, ["--i" as string]: i }} />)}
      </div>
    </div>
  );
}

/** Placeholder for a tab that isn't built yet. */
function Soon({ name }: { name: string }) {
  return <section className="view"><Empty title="Coming soon"><p>The {name} tab is on its way.</p></Empty></section>;
}
