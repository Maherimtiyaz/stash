import type { Board, Home, Me, ReviewAction, Save, SaveChanges, Shelf, Week } from "./types";

const TOKEN_KEY = "stash_token";
let current: string | null = null;

/** Reads the sign-in token from ?t= (then removes it from the address bar) or from storage. */
export function takeToken(): string | null {
  const url = new URL(window.location.href);
  const fromUrl = url.searchParams.get("t");
  if (fromUrl) {
    setToken(fromUrl);
    url.searchParams.delete("t");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    return fromUrl;
  }
  try {
    current = localStorage.getItem(TOKEN_KEY);
  } catch {
    current = null;
  }
  return current;
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
      "Content-Type": "application/json",
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
