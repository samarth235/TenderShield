import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, hasToken, setToken, UNAUTHORIZED_EVENT, type Role, type User } from "../api/client";

type AuthState = {
  user: User | null;
  checking: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  can: (role: Role) => boolean;
};

const RANK: Record<Role, number> = { viewer: 0, officer: 1, admin: 2 };
const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(hasToken);

  // Resume a session that survived a page reload.
  useEffect(() => {
    if (!hasToken()) return;
    api.me().then(setUser, () => setToken(null)).finally(() => setChecking(false));
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    qc.clear();
  }, [qc]);

  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      qc.clear();
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onExpired);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onExpired);
  }, [qc]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.login(email, password);
    setToken(r.access_token);
    setUser(r.user);
  }, []);

  const can = useCallback((role: Role) => !!user && RANK[user.role] >= RANK[role], [user]);

  return <AuthCtx.Provider value={{ user, checking, login, logout, can }}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
