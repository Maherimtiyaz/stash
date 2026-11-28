import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import type { Board, Me } from "./types";

interface Ctx {
  me: Me;
  boards: Board[];
  refreshBoards: () => Promise<void>;
  /** Bumped after any change, so open views refetch. */
  version: number;
  changed: () => void;
  openSave: (id: number) => void;
  closeSave: () => void;
  openId: number | null;
  remindersOpen: boolean;
  setRemindersOpen: (open: boolean) => void;
  importOpen: boolean;
  setImportOpen: (open: boolean) => void;
  toast: (msg: string) => void;
  toastMsg: string;
}

const AppCtx = createContext<Ctx | null>(null);

export function AppProvider({ me, children }: { me: Me; children: ReactNode }) {
  const [boards, setBoards] = useState<Board[]>([]);
  const [version, setVersion] = useState(0);
  const [openId, setOpenId] = useState<number | null>(null);
  const [remindersOpen, setRemindersOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [toastMsg, setToastMsg] = useState("");
  const timer = useRef<number>();

  const refreshBoards = useCallback(async () => setBoards(await api.boards()), []);
  useEffect(() => {
    refreshBoards().catch(() => undefined);
  }, [refreshBoards, version]);

  const toast = useCallback((msg: string) => {
    setToastMsg(msg);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToastMsg(""), 2000);
  }, []);

  const value: Ctx = {
    me,
    boards,
    refreshBoards,
    version,
    changed: () => setVersion((v) => v + 1),
    openSave: setOpenId, // a state setter, so it never changes between renders
    closeSave: () => setOpenId(null),
    openId,
    remindersOpen,
    setRemindersOpen,
    importOpen,
    setImportOpen,
    toast,
    toastMsg,
  };
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApp(): Ctx {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside AppProvider");
  return c;
}

/** Loads data for a view and reloads it whenever something changes. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]): { data: T | null; error: string; reload: () => void } {
  const { version } = useApp();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [n, setN] = useState(0);
  useEffect(() => {
    let live = true;
    load()
      .then((d) => live && (setData(d), setError("")))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version, n]);
  return { data, error, reload: () => setN((x) => x + 1) };
}
