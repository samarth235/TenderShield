import { ChevronRight, ExternalLink, FileDiff, Flag, Info, Lock, Search, ShieldAlert, ShieldCheck, Sparkles, ThumbsUp } from "lucide-react";
import type { ReactNode } from "react";

import { api } from "../api/client";
import type {
  DocumentVersion,
  FieldChange,
  ReviewDecision,
  VersionComparison,
  VersionExplanation,
  VersionStatus,
  VersionVerification,
} from "../api/types";
import { MST_TESTNET_EXPLORER } from "../blockchain/config";
import type { EvidenceRecord } from "../blockchain/wallet";
import { fmtDateTime, shortHash, type Tone } from "../lib/format";
import { Badge, Button, Callout, Card } from "./ui";

/* ---------------------------------------------------------------- shared helpers */

export const OPEN_STATUSES: VersionStatus[] = ["PENDING_REVIEW", "VERIFICATION_REQUESTED", "FLAGGED"];

const STATUS_LABEL: Record<VersionStatus, [string, Tone]> = {
  ACTIVE: ["Official", "pass"],
  SUPERSEDED: ["Historical", "na"],
  PENDING_REVIEW: ["Pending review", "accent"],
  VERIFICATION_REQUESTED: ["Verification required", "medium"],
  FLAGGED: ["Flagged for investigation", "high"],
};

export const VersionStatusBadge = ({ status }: { status: VersionStatus }) => (
  <Badge tone={STATUS_LABEL[status][1]}>{STATUS_LABEL[status][0]}</Badge>
);

/** An MST record is only trusted when both the record id and the SHA-256 match the version. */
export const chainMatches = (v: DocumentVersion, record: EvidenceRecord | null | undefined) =>
  !!record && !!v.chain_payload && record.caseId === v.chain_payload.case_id && record.evidenceHash.toLowerCase() === `0x${v.sha256}`.toLowerCase();

function MstCell({ version, record, configured }: { version: DocumentVersion; record: EvidenceRecord | null | undefined; configured: boolean }) {
  if (!version.chain_payload) return <span className="muted" title="Not sealed yet - accepted versions are sealed in a snapshot">—</span>;
  if (!configured) return <Badge tone="outline" title="Sealed in a snapshot; MST contract not configured">Sealed</Badge>;
  if (record === undefined) return <span className="muted">…</span>;
  if (!record) return <Badge tone="outline" title="Sealed off-chain; not yet committed on MST">Not on MST</Badge>;
  return chainMatches(version, record) ? <Badge tone="pass">MST ✓</Badge> : <Badge tone="fail">MST ≠</Badge>;
}

/* ---------------------------------------------------------------- story rail */

export type StoryStep = { title: string; sub: string; state: "done" | "bad" | "todo" };

export function StoryRail({ steps }: { steps: StoryStep[] }) {
  const next = steps.findIndex((s) => s.state === "todo");
  return (
    <div className="story" aria-label="Integrity demonstration steps">
      {steps.map((s, i) => (
        <div key={s.title} className={`story__step${s.state === "done" ? " story__step--done" : s.state === "bad" ? " story__step--bad" : i === next ? " story__step--next" : ""}`}>
          <span className="story__num">
            {s.state === "done" ? "✓" : s.state === "bad" ? "⚠" : i + 1} · STEP {i + 1}
          </span>
          <span className="story__title">{s.title}</span>
          <span className="muted" style={{ fontSize: 11.5, lineHeight: 1.35 }}>
            {s.sub}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- version seal */

export function VersionSeal({
  version,
  result,
  record,
  children,
}: {
  version: DocumentVersion | null;
  result: VersionVerification | null;
  record: EvidenceRecord | null | undefined;
  children?: ReactNode;
}) {
  const chainDisagrees = !!result && !!record && !!version && record.caseId === version.chain_payload?.case_id && record.evidenceHash.toLowerCase() !== `0x${result.current_sha256 ?? ""}`.toLowerCase();
  const state = !result ? "idle" : result.status === "INTEGRITY_MISMATCH" || chainDisagrees ? "bad" : result.status === "NEW_VERSION_DETECTED" ? "info" : "ok";
  const Icon = state === "ok" ? ShieldCheck : state === "bad" ? ShieldAlert : state === "info" ? Info : Lock;
  const onChain = !!version && chainMatches(version, record);
  const headline = !result
    ? version
      ? `Ready to verify ${version.label}`
      : "Select a document version"
    : state === "bad"
      ? "⚠ Integrity mismatch"
      : state === "info"
        ? "ℹ New version detected"
        : `✓ ${result.headline}${onChain ? " · on MST" : ""}`;
  const color = state === "ok" ? "var(--pass)" : state === "bad" ? "var(--fail)" : state === "info" ? "var(--accent)" : "var(--ink)";
  return (
    <div className={`seal seal--${state}`} key={result?.verified_at ?? "idle"}>
      <div className="seal__icon">
        <Icon size={44} strokeWidth={1.6} />
      </div>
      <div className="stack stack--sm" style={{ minWidth: 0 }}>
        <span className="section-label">
          {version ? `${version.filename} · ${version.label}` : "Document version"}
          {result && ` · checked ${fmtDateTime(result.verified_at)}`}
        </span>
        <span className="seal__status" style={{ color }}>
          {headline}
        </span>
        {result && <p style={{ fontSize: 13.5, margin: 0 }}>{chainDisagrees ? "The stored file no longer matches the SHA-256 recorded on MST for this version." : result.explanation}</p>}
        {version && (
          <div className="hash-compare">
            <span className="muted" style={{ fontSize: 12 }}>
              Recorded {version.label}
            </span>
            <span className="hash">{version.sha256}</span>
            {result && (
              <>
                <span className="muted" style={{ fontSize: 12 }}>
                  Stored file now
                </span>
                <span className={`hash${result.match ? "" : " hash--mismatch"}`}>{result.current_sha256 ?? "file missing"}</span>
              </>
            )}
            {record && version.chain_payload && record.caseId === version.chain_payload.case_id && (
              <>
                <span className="muted" style={{ fontSize: 12 }}>
                  MST record
                </span>
                <span className="hash">{record.evidenceHash.slice(2)}</span>
              </>
            )}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- history table */

export function VersionTable({
  versions,
  selected,
  onSelect,
  records,
  configured,
}: {
  versions: DocumentVersion[];
  selected: number | null;
  onSelect: (v: number) => void;
  records: Record<string, EvidenceRecord | null | undefined>;
  configured: boolean;
}) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Version</th>
          <th>Created</th>
          <th>SHA-256</th>
          <th>Status</th>
          <th>MST</th>
        </tr>
      </thead>
      <tbody>
        {[...versions].reverse().map((v) => (
          <tr key={v.version_id} className={`version-row${v.version === selected ? " version-row--selected" : ""}`} onClick={() => onSelect(v.version)}>
            <td>
              <b className="mono">{v.label}</b>
            </td>
            <td style={{ fontSize: 12.5 }}>
              {fmtDateTime(v.created_at)}
              <div className="muted" style={{ fontSize: 11.5 }}>
                {v.created_by}
              </div>
            </td>
            <td className="mono" style={{ fontSize: 12 }}>
              {shortHash(v.sha256, 4)}
            </td>
            <td>
              <VersionStatusBadge status={v.status} />
            </td>
            <td>
              <MstCell version={v} record={v.chain_payload ? records[v.chain_payload.case_id] : null} configured={configured} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function VersionDetails({ version, txHash }: { version: DocumentVersion; txHash: string }) {
  return (
    <dl className="kv">
      <dt>Version</dt>
      <dd>
        <span className="mono">{version.version_id}</span>
        {version.parent_version_id && <span className="muted"> · compared with {version.parent_version_id.split("@")[1].toUpperCase()}</span>}
      </dd>
      <dt>Timestamp</dt>
      <dd>{fmtDateTime(version.created_at)}</dd>
      <dt>Uploaded by</dt>
      <dd>{version.created_by}</dd>
      <dt>SHA-256</dt>
      <dd className="hash" style={{ fontSize: 11.5 }}>
        {version.sha256}
      </dd>
      <dt>Sealed in</dt>
      <dd className="mono" style={{ fontSize: 12 }}>
        {version.committed_in_snapshots?.length ? version.committed_in_snapshots.join(", ") : "not sealed yet"}
      </dd>
      <dt>MST record</dt>
      <dd className="mono" style={{ fontSize: 12, overflowWrap: "anywhere" }}>
        {version.chain_payload?.case_id ?? "created when the version is sealed"}
      </dd>
      {txHash && (
        <>
          <dt>Transaction</dt>
          <dd>
            <a className="mono" href={`${MST_TESTNET_EXPLORER}/tx/${txHash}`} target="_blank" rel="noreferrer" style={{ fontSize: 12, overflowWrap: "anywhere" }}>
              {shortHash(txHash, 8)} <ExternalLink size={11} />
            </a>
          </dd>
        </>
      )}
      <dt>Review status</dt>
      <dd>
        <VersionStatusBadge status={version.status} />
      </dd>
    </dl>
  );
}

/* ---------------------------------------------------------------- change review */

function ImpactBadge({ change }: { change: FieldChange }) {
  const rule = change.rule_check?.rule_id;
  switch (change.impact) {
    case "rule_failed":
      return <Badge tone="fail">Requirement not met · {rule}</Badge>;
    case "routine":
      return <Badge tone="pass">Consistent with renewal</Badge>;
    case "eligibility":
      return <Badge tone="medium">Eligibility · {rule}</Badge>;
    case "verify":
      return <Badge tone="unknown">Verification required</Badge>;
    default:
      return <Badge tone="outline">Informational</Badge>;
  }
}

export function ChangeTable({ comparison }: { comparison: VersionComparison }) {
  return (
    <>
      <table className="table">
        <thead>
          <tr>
            <th>Field</th>
            <th>{comparison.from_version}</th>
            <th>{comparison.to_version}</th>
            <th>Deterministic assessment</th>
          </tr>
        </thead>
        <tbody>
          {comparison.changes.map((c) => (
            <tr key={c.field}>
              <td style={{ fontSize: 13 }}>
                <b>{c.label}</b>
                {c.new_source && <div className="muted" style={{ fontSize: 11.5 }}>p.{c.new_source.page}</div>}
              </td>
              <td className="mono diff-old" style={{ fontSize: 12.5, whiteSpace: "nowrap" }}>
                {c.old_display}
              </td>
              <td className="mono diff-new" style={{ fontSize: 12.5, whiteSpace: "nowrap" }}>
                {c.new_display}
              </td>
              <td style={{ fontSize: 12 }}>
                <ImpactBadge change={c} />
                <div className="muted" style={{ marginTop: 4, maxWidth: "38ch" }}>
                  {c.note}
                </div>
              </td>
            </tr>
          ))}
          {comparison.changes.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                No structured field could be extracted as changed{comparison.text_changes.length ? "; see text changes below." : "."}
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {(comparison.unchanged.length > 0 || comparison.text_changes.length > 0) && (
        <details className="disclosure" style={{ margin: 12 }}>
          <summary>
            <ChevronRight size={14} className="disclosure__chev" />
            {comparison.unchanged.length} fields unchanged · {comparison.text_changes.length} other text change(s)
          </summary>
          <div className="stack stack--sm" style={{ padding: 12, fontSize: 12.5 }}>
            {comparison.text_changes.map((t, i) => (
              <div key={i} className="mono" style={{ color: t.change_type === "added" ? "var(--pass)" : "var(--fail)" }}>
                {t.change_type === "added" ? "+" : "−"} p.{t.page} {t.text}
              </div>
            ))}
            <div className="muted">Unchanged: {comparison.unchanged.map((u) => u.label).join(", ")}</div>
          </div>
        </details>
      )}
    </>
  );
}

export function ExplanationPanel({ explanation }: { explanation: VersionExplanation }) {
  const facts = explanation.integrity_facts;
  return (
    <div className="stack stack--sm">
      <div className="row" style={{ gap: 8 }}>
        <Sparkles size={15} color="var(--accent)" />
        <b style={{ fontSize: 13 }}>Explanation</b>
        <Badge tone={explanation.method === "llm" ? "accent" : "outline"}>{explanation.method === "llm" ? `Claude · ${explanation.model}` : "Rule-based"}</Badge>
        <span className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>
          Hashes differ ✓ · {facts.from_version.label} unchanged {facts.historical_version_unchanged ? "✓" : "✗"}
        </span>
      </div>
      <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.55 }}>{explanation.summary}</p>
      {explanation.auditor_checks.length > 0 && (
        <div>
          <span className="section-label">Auditor should verify</span>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 13 }}>
            {explanation.auditor_checks.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      {explanation.warnings.map((w) => (
        <Callout key={w} tone="warn">
          {w}
        </Callout>
      ))}
      <span className="muted" style={{ fontSize: 11.5 }}>
        {explanation.guardrail}
      </span>
    </div>
  );
}

export function ReviewActions({
  version,
  auditor,
  onAuditor,
  notes,
  onNotes,
  busy,
  onDecide,
}: {
  version: DocumentVersion;
  auditor: string;
  onAuditor: (v: string) => void;
  notes: string;
  onNotes: (v: string) => void;
  busy: ReviewDecision | null;
  onDecide: (d: ReviewDecision) => void;
}) {
  if (!OPEN_STATUSES.includes(version.status))
    return (
      <Callout tone={version.status === "ACTIVE" ? "ok" : undefined}>
        Auditor decision recorded: <b>{STATUS_LABEL[version.status][0]}</b>. The decision is an entry in the hash-chained audit trail.
      </Callout>
    );
  const disabled = !auditor.trim() || !!busy;
  return (
    <div className="stack stack--sm">
      <div className="row row--between">
        <span className="section-label">Auditor decision · {version.label}</span>
        <VersionStatusBadge status={version.status} />
      </div>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input className="input" style={{ flex: "0 0 180px" }} value={auditor} onChange={(e) => onAuditor(e.target.value)} placeholder="Auditor name" aria-label="Auditor name" />
        <input className="input" style={{ flex: 1 }} value={notes} onChange={(e) => onNotes(e.target.value)} placeholder="Notes for the audit trail (optional)" aria-label="Notes" />
      </div>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <Button variant="brand" icon={<ThumbsUp size={15} />} disabled={disabled} loading={busy === "ACCEPT"} onClick={() => onDecide("ACCEPT")}>
          Accept new version
        </Button>
        <Button icon={<Search size={15} />} disabled={disabled || version.status === "VERIFICATION_REQUESTED"} loading={busy === "REQUEST_VERIFICATION"} onClick={() => onDecide("REQUEST_VERIFICATION")}>
          Request verification
        </Button>
        <Button variant="danger" icon={<Flag size={15} />} disabled={disabled || version.status === "FLAGGED"} loading={busy === "FLAG_FOR_INVESTIGATION"} onClick={() => onDecide("FLAG_FOR_INVESTIGATION")}>
          Flag for investigation
        </Button>
      </div>
      {!auditor.trim() && <span className="muted" style={{ fontSize: 12 }}>Enter the auditor name to record a decision. Nothing is accepted automatically.</span>}
    </div>
  );
}

export function ChangeReviewCard({
  comparison,
  explanation,
  loading,
  error,
  children,
  docId,
}: {
  comparison: VersionComparison | undefined;
  explanation: VersionExplanation | undefined;
  loading: boolean;
  error: unknown;
  children: ReactNode;
  docId: string;
}) {
  return (
    <Card
      title={comparison ? `What changed · ${comparison.from_version} → ${comparison.to_version}` : "What changed"}
      icon={<FileDiff size={15} />}
      flush
      actions={
        comparison && (
          <a className="btn btn--sm" href={api.versionFileUrl(docId, Number(comparison.to_version.slice(1)))} target="_blank" rel="noreferrer">
            {comparison.to_version} PDF <ExternalLink size={12} />
          </a>
        )
      }
    >
      {loading && <p className="muted" style={{ padding: 16 }}>Comparing versions and preparing the explanation…</p>}
      {!!error && <div style={{ padding: 16 }}><Callout tone="danger">Could not compare versions: {String(error)}</Callout></div>}
      {comparison && <ChangeTable comparison={comparison} />}
      {explanation && (
        <div style={{ padding: 16, borderTop: "1px solid var(--line)" }}>
          <ExplanationPanel explanation={explanation} />
        </div>
      )}
      {comparison && <div style={{ padding: 16, borderTop: "1px solid var(--line)" }}>{children}</div>}
    </Card>
  );
}
