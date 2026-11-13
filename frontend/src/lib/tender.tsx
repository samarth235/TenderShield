import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

const KEY = "ts-current-tender";

type Ctx = { tid: string | null; setTid: (tid: string | null) => void };
const TenderCtx = createContext<Ctx>({ tid: null, setTid: () => {} });

function readSaved(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** Holds the tender the user is working on. Nothing is preselected: a fresh install starts empty. */
export function TenderProvider({ children }: { children: ReactNode }) {
  const [tid, setState] = useState<string | null>(readSaved);
  const setTid = useCallback((next: string | null) => {
    setState(next);
    try {
      if (next) localStorage.setItem(KEY, next);
      else localStorage.removeItem(KEY);
    } catch {
      /* storage unavailable */
    }
  }, []);
  return <TenderCtx.Provider value={{ tid, setTid }}>{children}</TenderCtx.Provider>;
}

export const useCurrentTender = () => useContext(TenderCtx);

/** The selected tender id; empty string when none is selected (queries are disabled in that case). */
export const useTid = () => useContext(TenderCtx).tid ?? "";
