import { useEffect, useState } from "react";
import { ApiError, api, setToken, signInOnLoad, signInWithLink, signOut } from "./api";
import { ImportPanel } from "./components/ImportPanel";
import { RemindersPanel } from "./components/RemindersPanel";
import { Viewer } from "./components/Viewer";
import { Icon, Spinner, type IconName } from "./components/ui";
import { AppProvider, useApp } from "./store";
import type { Me } from "./types";
import { BoardsView } from "./views/BoardsView";
import { PlanView } from "./views/PlanView";
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

  const [notice, setNotice] = useState("");
  const signIn = () => {
    setState("loading");
    signInOnLoad()
      .then((ok) => (ok ? api.me() : Promise.reject(new ApiError(401, ""))))
      .then((m) => (setMe(m), setState("ready")))
      .catch((e: Error) => {
        if (e instanceof ApiError && e.status === 401) {
          setToken(null);
          setNotice(e.message);
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
  if (state === "signed-out" || !me) return <SignIn onDone={signIn} notice={notice} />;
  return (
    <AppProvider me={me}>
      <Shell />
    </AppProvider>
  );
}

function Shell() {
  const { toastMsg, closeSave, openSave, setRemindersOpen } = useApp();
  // Reminder links end in ?open=<save id>: open that save, then tidy the address bar.
  useEffect(() => {
    const url = new URL(window.location.href);
    const id = Number(url.searchParams.get("open"));
    if (id > 0) openSave(id);
    if (url.searchParams.has("open")) {
      url.searchParams.delete("open");
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
  }, [openSave]);
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
        <button className="topbar-btn" onClick={() => setRemindersOpen(true)} aria-label="Reminders"><Icon name="bell" size={18} /><span>Reminders</span></button>
        <button className="signout" onClick={() => signOut().finally(() => window.location.replace(window.location.pathname))}>Sign out</button>
      </header>
      <main className="main" id="main">
        {tab === "search" && <SearchView />}
        {tab === "rediscover" && <RediscoverView />}
        {tab === "boards" && <BoardsView />}
        {tab === "plan" && <PlanView />}
      </main>
      <nav className="dock" aria-label="Sections">
        {TABS.map((t) => (
          <button key={t.id} className="dock-btn" aria-current={tab === t.id ? "page" : undefined} onClick={() => go(t.id)}>
            <Icon name={t.icon} size={22} /><span>{t.label}</span>
          </button>
        ))}
      </nav>
      <Viewer />
      <RemindersPanel />
      <ImportPanel />
      {toastMsg && <div className="toast" role="status" key={toastMsg}>{toastMsg}</div>}
    </div>
  );
}

function SignIn({ onDone, notice }: { onDone: () => void; notice: string }) {
  const [link, setLink] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    const m = link.match(/[?&]t=([^&#\s]+)/) ?? link.trim().match(/^(l_[\w-]{16,})$/);
    if (!m) return setErr("That doesn't look like a Stash sign-in link. It contains ?t= followed by a code.");
    setBusy(true);
    try {
      await signInWithLink(decodeURIComponent(m[1]));
      onDone();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="signin">
      <div className="signin-card">
        <span className="wordmark big">stash<i>✦</i></span>
        <h1>Your saves,<br />finally findable.</h1>
        {notice && <p className="notice" role="alert">{notice}</p>}
        <p>Stash signs you in with the private link <b>@stash</b> sends you on Instagram. Each link works once, for 24 hours. Send <code>LIBRARY</code> to @stash for a fresh one.</p>
        <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <label htmlFor="link">Or paste your link</label>
          <input id="link" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://…/app/?t=…" autoComplete="off" />
          {err && <p className="error">{err}</p>}
          <button className="fat fat-ink" type="submit" disabled={!link.trim() || busy}>{busy ? "Signing in…" : "Open my stash"}</button>
        </form>
        <p className="meta">No account? Stash is invite-only. Ask whoever told you about it for an invite.</p>
      </div>
      <div className="signin-art" aria-hidden="true">
        {["#ff5a1f", "#3d5afe", "#ffc83d", "#ff6fb5", "#19c37d"].map((c, i) => <span key={c} style={{ background: c, ["--i" as string]: i }} />)}
      </div>
    </div>
  );
}
