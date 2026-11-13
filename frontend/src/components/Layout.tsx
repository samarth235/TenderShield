import {
  Boxes,
  Fingerprint,
  Gauge,
  LogOut,
  Grid3x3,
  Network,
  ScanSearch,
  ShieldAlert,
  Upload,
} from "lucide-react";
import { type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../lib/auth";
import { useFindings, useTender, useTenders, useTid } from "../lib/hooks";
import { useCurrentTender } from "../lib/tender";
import { NotLoaded } from "./NotLoaded";
import { Badge, Button } from "./ui";

type NavItem = { to: string; label: string; icon: ReactNode };

// Primary objective: restructure the procurement so SMEs can compete.
const PRIMARY: NavItem[] = [
  { to: "/", label: "Tenders", icon: <Upload size={16} /> },
  { to: "/restructuring", label: "Restructuring plan", icon: <Boxes size={16} /> },
];

// Secondary objective: assurance on the bids received.
const ASSURANCE: NavItem[] = [
  { to: "/assurance", label: "Assurance overview", icon: <Gauge size={16} /> },
  { to: "/compliance", label: "Rules & compliance", icon: <Grid3x3 size={16} /> },
  { to: "/graph", label: "Relationship graph", icon: <Network size={16} /> },
  { to: "/intelligence", label: "Bid intelligence", icon: <ScanSearch size={16} /> },
  { to: "/findings", label: "Findings", icon: <ShieldAlert size={16} /> },
  { to: "/integrity", label: "Evidence integrity", icon: <Fingerprint size={16} /> },
];

export function BrandMark() {
  return (
    <svg className="brand__mark" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="#005EA2" />
      <path d="M16 5 7 8.5v6.8c0 5.6 3.8 10.1 9 11.7 5.2-1.6 9-6.1 9-11.7V8.5L16 5Z" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinejoin="round" />
      <path d="M11.5 15.5h9M16 11v9" stroke="#FFFFFF" strokeWidth="1.4" strokeLinecap="round" opacity=".45" />
      <circle cx="16" cy="15.5" r="2.6" fill="#FFFFFF" />
    </svg>
  );
}

function TenderPicker() {
  const tenders = useTenders();
  const { tid, setTid } = useCurrentTender();
  const navigate = useNavigate();
  return (
    <select
      className="select"
      aria-label="Current tender"
      style={{ maxWidth: 360 }}
      value={tid ?? ""}
      onChange={(e) => {
        setTid(e.target.value || null);
        if (!e.target.value) navigate("/");
      }}
    >
      <option value="">{tenders.data?.length ? "Select a tender…" : "No tenders uploaded"}</option>
      {tenders.data?.map((t) => (
        <option key={t.tender_id} value={t.tender_id}>
          {t.tender_id} · {t.title}
        </option>
      ))}
    </select>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <div className="user-menu">
      <span title={user.email}>{user.name || user.email}</span>
      <Badge tone={user.role === "viewer" ? "outline" : "brand"}>{user.role}</Badge>
      <Button className="icon-btn" onClick={logout} aria-label="Sign out" title="Sign out" icon={<LogOut size={15} />} />
    </div>
  );
}

export function Layout() {
  const tid = useTid();
  const tender = useTender();
  const findings = useFindings();
  const location = useLocation();

  const openSignals = findings.data?.filter((f) => f.category === "INVESTIGATION_SIGNAL" && ["HIGH", "MEDIUM"].includes(f.level)).length;
  // Every page except the tender list works on a selected tender.
  const needsTender = location.pathname !== "/" && !tid;

  const link = (item: NavItem) => (
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
  );

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <BrandMark />
          <div>
            <div className="brand__name">TenderShield</div>
            <div className="brand__tag">Procurement restructuring</div>
          </div>
        </div>
        <nav className="nav">
          <div className="nav__label">Restructuring workflow</div>
          {PRIMARY.map(link)}
          <div className="nav__label" style={{ marginTop: 14 }}>Bid assurance</div>
          {ASSURANCE.map(link)}
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar__tender">
            {tender.data ? (
              <Badge tone="outline">{tender.data.status.replace(/_/g, " ").toLowerCase()}</Badge>
            ) : null}
            <TenderPicker />
          </div>
          <div className="topbar__spacer" />
          <UserMenu />
        </header>
        <main className="content">{needsTender ? <NotLoaded what="tender" /> : <Outlet />}</main>
      </div>
    </div>
  );
}
