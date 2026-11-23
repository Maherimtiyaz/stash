import { useEffect, useState } from "react";
import { api } from "../api";
import { pushState, turnOffPush, turnOnPush, type PushState } from "../lib/push";
import { remindLabel, shelfLabel } from "../lib/format";
import { useApp, useLoad } from "../store";
import { Icon, Spinner } from "./ui";

const TEST_LABEL: Record<string, string> = { dm: "Instagram DM", push: "Notifications", email: "Email" };

/** Where reminders go: Instagram DM (when allowed), this device, or email. Plus a test button and upcoming list. */
export function RemindersPanel() {
  const { remindersOpen, setRemindersOpen, me, toast, openSave, changed } = useApp();
  const settings = useLoad(() => (remindersOpen ? api.reminders() : Promise.resolve(null)), [remindersOpen]);
  const [push, setPush] = useState<PushState | null>(null);
  const [email, setEmail] = useState(me.email ?? "");
  const [busy, setBusy] = useState("");
  const [test, setTest] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    if (!remindersOpen) return;
    setTest(null);
    pushState().then(setPush).catch(() => setPush("unsupported"));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setRemindersOpen(false);
    window.addEventListener("keydown", onKey);
    document.body.classList.add("locked");
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.classList.remove("locked");
    };
  }, [remindersOpen, setRemindersOpen]);
  useEffect(() => {
    if (settings.data) setEmail(settings.data.channels.email.address);
  }, [settings.data]);

  if (!remindersOpen) return null;
  const s = settings.data;

  async function run(label: string, fn: () => Promise<unknown>, done?: string) {
    setBusy(label);
    try {
      await fn();
      if (done) toast(done);
      settings.reload();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  const pushNote: Record<PushState, string> = {
    on: "On for this device.",
    off: "Get a notification on this phone or computer, even when Stash is closed.",
    blocked: "Notifications are blocked for this site. Allow them in your browser's site settings, then try again.",
    unsupported: "This browser can't show notifications. Try Chrome, Edge, Firefox or Safari.",
    "needs-install": "On iPhone: tap Share, then Add to Home Screen. Open Stash from your home screen and turn this on there.",
  };

  return (
    <div className="viewer-wrap" onClick={(e) => e.target === e.currentTarget && setRemindersOpen(false)}>
      <div className="viewer reminders" role="dialog" aria-modal="true" aria-label="Reminders">
        <button className="close" onClick={() => setRemindersOpen(false)} aria-label="Close"><Icon name="x" /></button>
        <header className="page-head">
          <span className="kicker">Reminders</span>
          <h2 className="mega small">Where nudges go</h2>
          <p className="lede">When a reminder is due, Stash uses the first option that works, in this order.</p>
        </header>
        {!s && !settings.error && <Spinner />}
        {settings.error && <p className="error">{settings.error}</p>}
        {s && (
          <>
            <ol className="channels">
              <li className="channel">
                <div className="channel-head"><b>Instagram DM</b>
                  <span className={`state ${s.channels.dm.open ? "ok" : "off"}`}>{s.channels.dm.open ? "Open" : "Closed"}</span></div>
                <p>{s.channels.dm.open && s.channels.dm.until
                  ? <>Instagram lets @stash message you until <b>{remindLabel(s.channels.dm.until)}</b>.</>
                  : <>Instagram only lets @stash message you for 24 hours after you message it. Send any message to @stash to open it.</>}</p>
              </li>

              <li className="channel">
                <div className="channel-head"><b>Notifications on this device</b>
                  <span className={`state ${push === "on" ? "ok" : "off"}`}>{push === "on" ? "On" : "Off"}</span></div>
                <p>{push ? pushNote[push] : "Checking…"}{s.channels.push.devices > 0 && <> {s.channels.push.devices} device{s.channels.push.devices === 1 ? "" : "s"} signed up in total.</>}</p>
                {!s.channels.push.public_key ? (
                  <p className="meta">Notifications aren't set up on this server yet (it needs VAPID keys).</p>
                ) : push === "off" || push === "blocked" ? (
                  <button className="pill" disabled={busy === "push"}
                    onClick={() => run("push", async () => setPush(await turnOnPush(s.channels.push.public_key)), "Notifications on for this device")}>
                    <Icon name="bell" size={14} />Turn on
                  </button>
                ) : push === "on" ? (
                  <button className="pill ghost" disabled={busy === "push"} onClick={() => run("push", async () => setPush(await turnOffPush()), "Notifications off for this device")}>Turn off</button>
                ) : null}
              </li>

              <li className="channel">
                <div className="channel-head"><b>Email</b>
                  <span className={`state ${s.channels.email.address ? "ok" : "off"}`}>{s.channels.email.address ? "On" : "Off"}</span></div>
                <form className="email-row" onSubmit={(e) => { e.preventDefault(); run("email", () => api.setEmail(email), email ? "Email saved" : "Email removed"); }}>
                  <label className="sr" htmlFor="remind-email">Email for reminders</label>
                  <input id="remind-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" maxLength={120} />
                  <button className="pill" type="submit" disabled={busy === "email" || email === s.channels.email.address}>Save</button>
                </form>
                {!s.channels.email.live && <p className="meta">Email isn't connected on this server yet, so nothing is sent for real.</p>}
              </li>
            </ol>

            <div className="test-row">
              <button className="fat fat-sun" disabled={busy === "test"} onClick={() => run("test", async () => setTest((await api.testReminder()).channels))}>
                <Icon name="bell" />{busy === "test" ? "Sending…" : "Send me a test"}
              </button>
              {test && (
                <ul className="test-results" aria-live="polite">
                  {Object.entries(test).map(([ch, res]) => (
                    <li key={ch} className={res.startsWith("sent") ? "ok" : "off"}><b>{TEST_LABEL[ch] ?? ch}:</b> {res}</li>
                  ))}
                </ul>
              )}
            </div>

            <section className="block">
              <h3>Coming up</h3>
              {s.upcoming.length === 0 ? <p className="meta">No reminders set. Open any save and tap “Nudge me”.</p> : (
                <ul className="upcoming">
                  {s.upcoming.map((u) => (
                    <li key={u.id}>
                      <button className="link-strong" onClick={() => { setRemindersOpen(false); openSave(u.id); }}>{u.caption.replace(/#\w+/g, "").trim() || "A save"}</button>
                      <span className="meta">{shelfLabel(u.category ?? "Unsorted")} · {remindLabel(u.remind_at)}</span>
                      <button className="pill ghost" onClick={() => run(`clear${u.id}`, () => api.update(u.id, { remind_at: null }).then(changed), "Reminder removed")}>Clear</button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
