import type { Board, Home, ImportRecord, ImportSummary, Me, ReminderSettings, ReviewAction, Save, SaveChanges, Shelf, Week } from "./types";

const TOKEN_KEY = "stash_token";
let current: string | null = null;

/** Removes ?t= from the address bar and returns it, so a one-time link isn't left in history. */
function takeLinkFromUrl(): string | null {
  const url = new URL(window.location.href);
  const link = url.searchParams.get("t");
  if (!link) return null;
  url.searchParams.delete("t");
  window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  return link;
}

/** The stored session, if any. */
export function storedSession(): string | null {
  try {
    current = localStorage.getItem(TOKEN_KEY);
  } catch {
    current = null;
  }
  return current?.startsWith("s_") ? current : null;
}

/** Swap a one-time sign-in link for a session and keep it. */
export async function signInWithLink(link: string): Promise<void> {
  const { token } = await call<{ token: string; expires_at: string }>("/session", { method: "POST", body: JSON.stringify({ link }) });
  setToken(token);
}

/**
 * Signs in on page load: a link in ?t= wins (and replaces any older session), otherwise the stored session.
 * Returns false when there is nothing to sign in with.
 */
export async function signInOnLoad(): Promise<boolean> {
  const link = takeLinkFromUrl();
  if (link) {
    await signInWithLink(link);
    return true;
  }
  return storedSession() !== null;
}

export async function signOut(): Promise<void> {
  try {
    if (current) await call("/session", { method: "DELETE" });
  } finally {
    setToken(null);
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: the token lives for this tab only */
  }
  current = token;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      // FormData sets its own multipart Content-Type.
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(current ? { Authorization: `Bearer ${current}` } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) {
    let message = `Something went wrong (${res.status}). Try again.`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  me: () => call<Me>("/me"),
  setEmail: (email: string) => call<{ email: string }>("/me", { method: "PATCH", body: json({ email }) }),
  setTimezone: (timezone: string) => call<{ timezone: string }>("/me", { method: "PATCH", body: json({ timezone }) }),
  reminders: () => call<ReminderSettings>("/reminders"),
  importExport: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<ImportSummary>("/import", { method: "POST", body: form });
  },
  imports: () => call<ImportRecord[]>("/imports"),
  undoImport: (id: number) => call<{ removed: number; piles_removed: number }>(`/imports/${id}`, { method: "DELETE" }),
  testReminder: () => call<{ sent: boolean; channels: Record<string, string> }>("/reminders/test", { method: "POST" }),
  pushSubscribe: (subscription: PushSubscriptionJSON) => call<{ ok: true }>("/push/subscribe", { method: "POST", body: json({ subscription }) }),
  pushUnsubscribe: (endpoint: string) => call<{ ok: true }>("/push/unsubscribe", { method: "POST", body: json({ endpoint }) }),
  home: () => call<Home>("/home"),
  search: (q: string) => call<{ query: string; results: Save[] }>(`/saves?q=${encodeURIComponent(q)}`),
  save: (id: number) => call<Save>(`/saves/${id}`),
  update: (id: number, changes: SaveChanges) => call<Save>(`/saves/${id}`, { method: "PATCH", body: json(changes) }),
  remove: (id: number) => call<{ ok: true }>(`/saves/${id}`, { method: "DELETE" }),
  shelves: () => call<Shelf[]>("/categories"),
  boards: () => call<Board[]>("/boards"),
  createBoard: (name: string) => call<Board>("/boards", { method: "POST", body: json({ name }) }),
  renameBoard: (id: number, name: string) => call<Board>(`/boards/${id}`, { method: "PATCH", body: json({ name }) }),
  deleteBoard: (id: number) => call<{ ok: true }>(`/boards/${id}`, { method: "DELETE" }),
  rediscover: () => call<Save[]>("/rediscover"),
  review: (id: number, action: ReviewAction) => call<Save>(`/saves/${id}/review`, { method: "POST", body: json({ action }) }),
  plan: (start?: string) => call<Week>(`/plan${start ? `?start=${start}` : ""}`),
};
