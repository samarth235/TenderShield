import {
  Fingerprint,
  Gauge,
  Grid3x3,
  Moon,
  Network,
  RefreshCw,
  ScanSearch,
  ShieldAlert,
  Sun,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { shortTitle } from "../lib/format";
import { useFindings, useHealth, useLoadDemo, useTender } from "../lib/hooks";
import { Badge, Button, useToast } from "./ui";

const NAV: { to: string; label: string; icon: ReactNode }[] = [
  { to: "/", label: "Overview", icon: <Gauge size={16} /> },
  { to: "/compliance", label: "Rules & compliance", icon: <Grid3x3 size={16} /> },
  { to: "/graph", label: "Relationship graph", icon: <Network size={16} /> },
  { to: "/intelligence", label: "Bid intelligence", icon: <ScanSearch size={16} /> },
  { to: "/findings", label: "Findings", icon: <ShieldAlert size={16} /> },
  { to: "/integrity", label: "Evidence integrity", icon: <Fingerprint size={16} /> },
];

export function BrandMark() {
  return (
    <svg className="brand__mark" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="#1f3a68" />
      <path d="M16 5 7 8.5v6.8c0 5.6 3.8 10.1 9 11.7 5.2-1.6 9-6.1 9-11.7V8.5L16 5Z" fill="none" stroke="#fff" strokeWidth="2" strokeLinejoin="round" />
      <path d="M11.5 15.5h9M16 11v9" stroke="#fff" strokeWidth="1.4" strokeLinecap="round" opacity=".45" />
      <circle cx="16" cy="15.5" r="2.6" fill="#fff" />
    </svg>
  );
}

function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    try {
      const saved = localStorage.getItem("ts-theme");
      if (saved === "light" || saved === "dark") return saved;
    } catch {
      /* storage unavailable */
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("ts-theme", theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "light" ? "dark" : "light"))] as const;
}

export function Layout() {
  const health = useHealth();
  const tender = useTender();
  const findings = useFindings();
  const load = useLoadDemo();
  const toast = useToast();
  const [theme, toggleTheme] = useTheme();

  const openSignals = findings.data?.filter((f) => f.category === "INVESTIGATION_SIGNAL" && ["HIGH", "MEDIUM"].includes(f.level)).length;
  const online = health.isSuccess;

  const reload = () =>
    load.mutate(undefined, {
      onSuccess: (r) =>
        toast(
          <span>
            Demo tender <b>{r.tender_id}</b> loaded and analysed in {Math.round(r.analysis?.duration_ms ?? 0)} ms
          </span>,
        ),
    });

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <BrandMark />
          <div>
            <div className="brand__name">TendorShield</div>
            <div className="brand__tag">Evidence intelligence</div>
          </div>
        </div>
        <nav className="nav">
          <div className="nav__label">Investigation workflow</div>
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"} className="nav__link">
              {item.icon}
              <span>{item.label}</span>
              {item.to === "/findings" && openSignals ? (
                <span className="nav__count nav__count--alert">{openSignals}</span>
              ) : item.to === "/findings" && findings.data ? (
                <span className="nav__count">{findings.data.length}</span>
              ) : (
                <span />
              )}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar__tender">
            {tender.data ? (
              <>
                <Badge tone="brand">{tender.data.tender_id}</Badge>
                <span className="topbar__title" title={tender.data.title}>
                  {shortTitle(tender.data.title)}
                </span>
                <Badge tone="outline">{tender.data.status.replace(/_/g, " ").toLowerCase()}</Badge>
              </>
            ) : (
              <span className="muted">No tender loaded</span>
            )}
          </div>
          <div className="topbar__spacer" />
          <Button
            variant={tender.data ? undefined : "brand"}
            icon={<RefreshCw size={15} />}
            loading={load.isPending}
            onClick={reload}
            disabled={!online}
          >
            {tender.data ? "Reload demo" : "Load demonstration tender"}
          </Button>
          <Button className="icon-btn" onClick={toggleTheme} aria-label="Toggle theme" icon={theme === "light" ? <Moon size={15} /> : <Sun size={15} />} />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
