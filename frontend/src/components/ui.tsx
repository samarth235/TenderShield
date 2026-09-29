import { AlertTriangle, CheckCircle2, ExternalLink, FileText, Info, Loader2, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api } from "../api/client";
import { humanize, levelTone, resultTone, statusTone, type Tone } from "../lib/format";

export function Badge({ tone = "outline", dot, children, title }: { tone?: Tone; dot?: boolean; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge--${tone}${dot ? " badge--dot" : ""}`} title={title}>
      {children}
    </span>
  );
}

export const LevelBadge = ({ level }: { level: string }) => (
  <Badge tone={levelTone(level)} dot>
    {level === "INSUFFICIENT_DATA" ? "Insufficient data" : level}
  </Badge>
);

export const ResultBadge = ({ result }: { result: string }) => (
  <Badge tone={resultTone(result)}>{result === "NOT_APPLICABLE" ? "N/A" : result}</Badge>
);

export const StatusBadge = ({ status }: { status: string }) => <Badge tone={statusTone(status)}>{humanize(status)}</Badge>;

export function Card({
  title,
  icon,
  actions,
  children,
  flush,
  className = "",
}: {
  title?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card__head">
          <h3 className="card__title">
            {icon}
            {title}
          </h3>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      <div className={`card__body${flush ? " card__body--flush" : ""}`}>{children}</div>
    </section>
  );
}

export function StatTile({ label, value, hint, icon, accent }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; accent?: string }) {
  return (
    <div className="card stat">
      <span className="stat__label">
        {icon}
        {label}
      </span>
      <span className="stat__value" style={accent ? { color: accent } : undefined}>
        {value}
      </span>
      {hint && <span className="stat__hint">{hint}</span>}
    </div>
  );
}

export function Button({
  variant,
  size,
  loading,
  icon,
  children,
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "brand" | "danger" | "ghost";
  size?: "sm" | "lg";
  loading?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button
      className={`btn${variant ? ` btn--${variant}` : ""}${size ? ` btn--${size}` : ""} ${className}`}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading ? <Loader2 size={15} className="spin" /> : icon}
      {children}
    </button>
  );
}

export function PageHead({ step, eyebrow, title, sub, actions }: { step?: string; eyebrow: string; title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <div className="page-head__eyebrow">
          {step && <span className="mono">{step}</span>}
          {eyebrow}
        </div>
        <h1>{title}</h1>
        {sub && <p className="page-head__sub">{sub}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      {icon}
      <h3>{title}</h3>
      {children && <p style={{ maxWidth: "52ch" }}>{children}</p>}
      {action}
    </div>
  );
}

export const Skeleton = ({ h = 16, w = "100%" }: { h?: number; w?: number | string }) => (
  <div className="skeleton" style={{ height: h, width: w }} />
);

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div className="stack">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} h={i === 0 ? 28 : 16} w={i === 0 ? "40%" : `${90 - i * 8}%`} />
      ))}
    </div>
  );
}

export function Meter({ value, max = 1, color, ticks = [] }: { value: number; max?: number; color: string; ticks?: number[] }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="meter" role="meter" aria-valuenow={value} aria-valuemax={max}>
      <div className="meter__fill" style={{ width: `${pct}%`, background: color }} />
      {ticks.map((t) => (
        <span key={t} className="meter__tick" style={{ left: `${(t / max) * 100}%` }} />
      ))}
    </div>
  );
}

export function DocLink({ documentId, page, label }: { documentId: string; page?: number | null; label?: string }) {
  return (
    <a className="doc-link" href={api.documentUrl(documentId, page)} target="_blank" rel="noreferrer">
      <FileText size={12} />
      {label ?? documentId}
      {page ? ` · p.${page}` : ""}
      <ExternalLink size={11} />
    </a>
  );
}

export function Callout({ tone, children }: { tone?: "warn" | "danger" | "ok" | "info"; children: ReactNode }) {
  const Icon = tone === "danger" ? XCircle : tone === "ok" ? CheckCircle2 : tone === "warn" ? AlertTriangle : Info;
  return (
    <div className={`callout${tone ? ` callout--${tone}` : ""}`}>
      <Icon size={16} />
      <div>{children}</div>
    </div>
  );
}

export function Drawer({ title, sub, onClose, children }: { title: ReactNode; sub?: ReactNode; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true">
        <header className="drawer__head">
          <div>
            <h3>{title}</h3>
            {sub && <div className="muted" style={{ marginTop: 4, fontSize: 13 }}>{sub}</div>}
          </div>
          <Button variant="ghost" className="icon-btn" onClick={onClose} aria-label="Close" icon={<X size={16} />} />
        </header>
        <div className="drawer__body">{children}</div>
      </aside>
    </>
  );
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="switch" title={label}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} aria-label={label} />
      <span className="switch__track" />
    </label>
  );
}

export function FamilyDot({ family }: { family: string }) {
  return <span className={`fam-dot fam--${family}`} />;
}

/* ---------------------------------------------------------------- toasts */

const ToastCtx = createContext<(msg: ReactNode) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState<ReactNode>(null);
  const show = useCallback((m: ReactNode) => setMsg(m), []);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 3800);
    return () => clearTimeout(t);
  }, [msg]);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {msg && (
        <div className="toast" role="status">
          <CheckCircle2 size={16} color="var(--brand)" />
          {msg}
        </div>
      )}
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
