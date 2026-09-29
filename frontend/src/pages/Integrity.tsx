import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Copy,
  Download,
  FileWarning,
  Fingerprint,
  Link2,
  Lock,
  RotateCcw,
  ShieldCheck,
  ShieldX,
  Stamp,
} from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Snapshot, Verification } from "../api/types";
import { ErrorCard, NotLoaded } from "../components/NotLoaded";
import { Badge, Button, Callout, Card, LoadingBlock, PageHead, useToast } from "../components/ui";
import { fmtDateTime, humanize, shortHash } from "../lib/format";
import { isNotLoaded, TID, useAuditLog, useSnapshots, useTender } from "../lib/hooks";

function Seal({ result, snapshot }: { result: Verification | null; snapshot: Snapshot | null }) {
  const state = !result ? "idle" : result.match ? "ok" : "bad";
  const Icon = state === "ok" ? ShieldCheck : state === "bad" ? ShieldX : Lock;
  return (
    <div className={`seal seal--${state}`} key={result?.verified_at ?? "idle"}>
      <div className="seal__icon">
        <Icon size={44} strokeWidth={1.6} />
      </div>
      <div className="stack stack--sm" style={{ minWidth: 0 }}>
        <span className="section-label">{result ? `Verified ${fmtDateTime(result.verified_at)}` : snapshot ? "Evidence committed" : "No evidence committed yet"}</span>
        <span className="seal__status" style={{ color: state === "ok" ? "var(--pass)" : state === "bad" ? "var(--fail)" : "var(--ink)" }}>
          {state === "ok" ? "✓ Integrity verified" : state === "bad" ? "✗ Integrity mismatch" : snapshot ? "Ready to verify" : "Finalise evidence to seal it"}
        </span>
        {snapshot && (
          <div className="hash-compare">
            <span className="muted" style={{ fontSize: 12 }}>
              Committed hash
            </span>
            <span className="hash">{result?.committed_hash ?? snapshot.bundle_hash}</span>
            {result && (
              <>
                <span className="muted" style={{ fontSize: 12 }}>
                  Current hash
                </span>
                <span className={`hash${result.match ? "" : " hash--mismatch"}`}>{result.current_hash}</span>
              </>
            )}
          </div>
        )}
        {result && !result.match && (
          <div className="stack stack--sm" style={{ marginTop: 8 }}>
            {result.changed_documents.map((d) => (
              <div key={d.document_id} className="callout callout--danger" style={{ alignItems: "center" }}>
                <FileWarning size={16} />
                <div>
                  <b>{d.filename}</b> changed since commitment
                  <div className="mono" style={{ fontSize: 11 }}>
                    {shortHash(d.committed_sha256)} → {shortHash(d.current_sha256)}
                  </div>
                </div>
              </div>
            ))}
            {result.changed_components.length > 0 && (
              <span className="muted" style={{ fontSize: 12 }}>
                Changed components: {result.changed_components.join(", ")}
              </span>
            )}
          </div>
        )}
        {result && <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>{result.note}</p>}
      </div>
    </div>
  );
}

export function Integrity() {
  const tender = useTender();
  const snapshots = useSnapshots();
  const audit = useAuditLog();
  const qc = useQueryClient();
  const toast = useToast();
  const [auditor, setAuditor] = useState(() => {
    try {
      return localStorage.getItem("ts-auditor") ?? "";
    } catch {
      return "";
    }
  });
  const [current, setCurrent] = useState<Snapshot | null>(null);
  const [result, setResult] = useState<Verification | null>(null);
  const [doc, setDoc] = useState("DOC-V001-COMP");

  useEffect(() => {
    if (!current && snapshots.data?.length) setCurrent(snapshots.data[snapshots.data.length - 1]);
  }, [snapshots.data, current]);
  // Snapshot list rows are summaries; fetch the full record (component hashes, chain payload) once selected.
  useEffect(() => {
    if (current && !current.chain_payload) api.snapshot(current.snapshot_id).then(setCurrent).catch(() => undefined);
  }, [current]);

  const finalize = useMutation({
    mutationFn: () => api.finalize(TID, auditor),
    onSuccess: (s) => {
      setCurrent(s);
      setResult(null);
      toast(
        <span>
          Evidence sealed · <span className="mono">{shortHash(s.bundle_hash, 4)}</span>
        </span>,
      );
      return qc.invalidateQueries({ queryKey: ["snapshots"] });
    },
  });
  const verify = useMutation({
    mutationFn: (sid: string) => api.verify(sid),
    onSuccess: setResult,
  });
  const tamper = useMutation({
    mutationFn: () => api.tamper(doc),
    onSuccess: (r) => toast(<span>{r.change} in <b>{r.filename}</b>. Now verify.</span>),
  });
  const restore = useMutation({
    mutationFn: api.restore,
    onSuccess: (r) => toast(<span>Restored {r.restored.length} document(s)</span>),
  });

  if (tender.isLoading) return <LoadingBlock rows={6} />;
  if (tender.error) return isNotLoaded(tender.error) ? <NotLoaded what="evidence" /> : <ErrorCard error={tender.error} />;
  const docs = tender.data!.documents;
  const dispositions = audit.data?.entries.filter((e) => e.action === "DISPOSITION").length ?? 0;
  const payload = current?.chain_payload;

  const steps = [
    { done: dispositions > 0, title: "Record auditor dispositions", body: `${dispositions} disposition(s) in the audit chain.` },
    { done: !!current, title: "Finalise the evidence package", body: "Freeze the rulebook, compliance results, findings, audit trail and document fingerprints into one SHA-256 hash." },
    { done: !!current, title: "Commit the hash on-chain", body: "The blockchain module stores only the chain payload: case id, evidence hash, audit head, timestamp." },
    { done: !!result, title: "Verify at any later time", body: "Recompute the hash from the stored evidence and compare it with the committed one." },
  ];

  return (
    <>
      <PageHead
        eyebrow="Evidence commitment + verification"
        title="Evidence integrity"
        sub="Sensitive documents stay off-chain. Only the fingerprint of the finalised evidence state is committed, so any later change to a document, finding or decision is detectable."
        actions={
          <a className="btn" href={api.dossierUrl(TID)} target="_blank" rel="noreferrer">
            <Download size={15} /> Dossier data (JSON)
          </a>
        }
      />

      <div className="grid grid--main-side">
        <div className="stack" style={{ gap: 18 }}>
          <Seal result={result} snapshot={current} />

          <div className="row">
            <Button variant="primary" size="lg" icon={<Fingerprint size={16} />} disabled={!current} loading={verify.isPending} onClick={() => current && verify.mutate(current.snapshot_id)}>
              Verify integrity
            </Button>
            {current && (
              <span className="muted" style={{ fontSize: 13 }}>
                Snapshot <span className="mono">{current.snapshot_id}</span> · {fmtDateTime(current.created_at)}
              </span>
            )}
          </div>

          <Card title="Tamper demonstration" icon={<FileWarning size={15} />}>
            <div className="stack">
              <p className="dim" style={{ fontSize: 13 }}>
                Simulate someone altering a stored evidence file after commitment (outside the normal workflow). Then verify.
              </p>
              <div className="row" style={{ flexWrap: "nowrap" }}>
                <select className="select" value={doc} onChange={(e) => setDoc(e.target.value)}>
                  {docs.map((d) => (
                    <option key={d.document_id} value={d.document_id}>
                      {d.filename}
                    </option>
                  ))}
                </select>
                <Button variant="danger" icon={<FileWarning size={15} />} loading={tamper.isPending} onClick={() => tamper.mutate()}>
                  Modify document
                </Button>
                <Button icon={<RotateCcw size={15} />} loading={restore.isPending} onClick={() => restore.mutate()}>
                  Restore
                </Button>
              </div>
              <Callout>
                Blockchain proves the committed evidence is unchanged. It does not prove the original documents were truthful or that a detected pattern was illegal.
              </Callout>
            </div>
          </Card>

          {current?.component_hashes && (
            <Card title="Evidence bundle" icon={<Stamp size={15} />} flush>
              <table className="table">
                <tbody>
                  {Object.entries(current.component_hashes).map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ width: 160 }}>{humanize(k)}</td>
                      <td className="hash" style={{ fontSize: 11.5 }}>
                        {v}
                      </td>
                      <td style={{ width: 90 }}>
                        {result && (result.changed_components.includes(k) ? <Badge tone="fail">changed</Badge> : <Badge tone="pass">intact</Badge>)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>

        <div className="stack" style={{ gap: 18 }}>
          <Card title="Commitment workflow" icon={<Lock size={15} />}>
            <div className="step-list">
              {steps.map((s, i) => (
                <div key={s.title} className="step-list__item">
                  <span className={`step-list__num${s.done ? " done" : ""}`}>{i + 1}</span>
                  <div>
                    <b style={{ fontSize: 13 }}>{s.title}</b>
                    <p className="muted" style={{ fontSize: 12.5 }}>
                      {s.body}
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <hr className="divider" style={{ margin: "14px 0" }} />
            <div className="stack stack--sm">
              <div className="field">
                <label htmlFor="fin-auditor">Finalising auditor</label>
                <input id="fin-auditor" className="input" value={auditor} onChange={(e) => setAuditor(e.target.value)} placeholder="Your name" />
              </div>
              <Button variant="brand" icon={<Stamp size={15} />} disabled={!auditor.trim()} loading={finalize.isPending} onClick={() => finalize.mutate()}>
                Finalise &amp; seal evidence
              </Button>
              {finalize.isError && <Callout tone="danger">{String(finalize.error)}</Callout>}
            </div>
          </Card>

          {payload && (
            <Card
              title="On-chain payload"
              icon={<Link2 size={15} />}
              actions={
                <Button size="sm" icon={<Copy size={13} />} onClick={() => navigator.clipboard?.writeText(JSON.stringify(payload, null, 2)).then(() => toast("Chain payload copied"))}>
                  Copy
                </Button>
              }
            >
              <pre className="code" style={{ margin: 0, fontSize: 11.5, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                {JSON.stringify(payload, null, 2)}
              </pre>
            </Card>
          )}

          <Card title="Audit chain" actions={audit.data && <Badge tone={audit.data.chain.valid ? "pass" : "fail"}>{audit.data.chain.valid ? "valid" : "broken"}</Badge>}>
            <div className="stack stack--sm">
              {audit.data?.entries.slice(-6).reverse().map((e) => (
                <div key={e.entry_id} className="row row--between" style={{ fontSize: 12.5 }}>
                  <span>
                    <span className="mono muted">#{e.entry_id}</span> {humanize(e.action)}
                  </span>
                  <span className="mono muted">{e.entry_hash.slice(0, 10)}…</span>
                </div>
              ))}
            </div>
          </Card>

          {snapshots.data && snapshots.data.length > 1 && (
            <Card title="Snapshots">
              <div className="stack stack--sm">
                {snapshots.data.map((s) => (
                  <button
                    key={s.snapshot_id}
                    className={`btn btn--sm${current?.snapshot_id === s.snapshot_id ? " btn--primary" : ""}`}
                    style={{ justifyContent: "space-between" }}
                    onClick={() => {
                      setCurrent(s);
                      setResult(null);
                    }}
                  >
                    <span className="mono">{s.snapshot_id}</span>
                    <span className="mono">{shortHash(s.bundle_hash, 4)}</span>
                  </button>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
