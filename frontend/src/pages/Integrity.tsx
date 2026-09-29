import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import {
  Anchor,
  ChevronRight,
  Copy,
  Download,
  ExternalLink,
  FilePen,
  FilePlus2,
  Fingerprint,
  History,
  Lock,
  RotateCcw,
  ShieldCheck,
  ShieldX,
  Stamp,
  Upload,
  Wallet,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import type { DocumentVersion, ReviewDecision, Snapshot, Verification, VersionVerification } from "../api/types";
import { MST_TESTNET_EXPLORER, TENDERSHIELD_CONTRACT_ADDRESS } from "../blockchain/config";
import { commitEvidenceToBlockchain, connectWallet, contractConfigured, getEvidence, walletError, type EvidenceRecord } from "../blockchain/wallet";
import { ErrorCard, NotLoaded } from "../components/NotLoaded";
import { Badge, Button, Callout, Card, LoadingBlock, PageHead, useToast } from "../components/ui";
import {
  ChangeReviewCard,
  chainMatches,
  OPEN_STATUSES,
  ReviewActions,
  StoryRail,
  VersionDetails,
  VersionSeal,
  VersionTable,
  type StoryStep,
} from "../components/versions";
import { fmtDateTime, humanize, shortHash } from "../lib/format";
import { isNotLoaded, TID, useAuditLog, useSnapshots, useTender, useVersionExplanation, useVersions } from "../lib/hooks";

const DEFAULT_DOCUMENT = "DOC-V001-COMP";
const txKey = (caseId: string) => `ts-mst-tx:${TENDERSHIELD_CONTRACT_ADDRESS}:${caseId}`;
const readTx = (caseId: string) => {
  try {
    return localStorage.getItem(txKey(caseId)) ?? "";
  } catch {
    return "";
  }
};
const writeTx = (caseId: string, hash: string) => {
  try {
    localStorage.setItem(txKey(caseId), hash);
  } catch {
    /* storage disabled */
  }
};

/** Snapshot-level seal: the whole evidence package (rulebook, findings, audit trail, document fingerprints). */
function Seal({ result, snapshot, chain, chainChecked }: { result: Verification | null; snapshot: Snapshot | null; chain: EvidenceRecord | null; chainChecked: boolean }) {
  const chainMatch = !!result && !!chain && chain.caseId === snapshot?.snapshot_id && chain.tenderId === snapshot?.tender_id && chain.evidenceHash.toLowerCase() === `0x${result.current_hash}`.toLowerCase() && chain.evidenceHash.toLowerCase() === `0x${snapshot?.bundle_hash}`.toLowerCase() && (!snapshot?.chain_payload || chain.auditHeadHash.toLowerCase() === `0x${snapshot.chain_payload.audit_head_hash}`.toLowerCase());
  const bad = !!result && (!result.match || (!!chain && !chainMatch));
  const state = !result ? "idle" : bad ? "bad" : result.status === "NEW_VERSION_DETECTED" ? "info" : chainMatch || !contractConfigured() ? "ok" : "idle";
  const Icon = state === "ok" || state === "info" ? ShieldCheck : state === "bad" ? ShieldX : Lock;
  const text = !result
    ? snapshot ? "Ready to verify" : "Finalise evidence to seal it"
    : bad
      ? "⚠ Integrity mismatch"
      : result.status === "NEW_VERSION_DETECTED"
        ? "ℹ Historically verified · new version detected"
        : chainMatch
          ? "✓ Blockchain integrity verified"
          : chainChecked
            ? "Backend hash verified · awaiting blockchain commitment"
            : "✓ Integrity verified (backend)";
  return (
    <div className={`seal seal--${state}`} key={result?.verified_at ?? "idle"} style={{ padding: 20, gridTemplateColumns: "72px 1fr" }}>
      <div className="seal__icon" style={{ width: 72, height: 72, borderRadius: 18 }}>
        <Icon size={34} strokeWidth={1.6} />
      </div>
      <div className="stack stack--sm" style={{ minWidth: 0 }}>
        <span className="section-label">{result ? `Checked ${fmtDateTime(result.verified_at)}` : snapshot ? `Snapshot ${snapshot.snapshot_id}` : "No evidence snapshot yet"}</span>
        <span className="seal__status" style={{ fontSize: 20, color: state === "ok" ? "var(--pass)" : state === "bad" ? "var(--fail)" : state === "info" ? "var(--accent)" : "var(--ink)" }}>
          {text}
        </span>
        {result?.explanation && <p style={{ margin: 0, fontSize: 13 }}>{result.explanation}</p>}
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
        {result && !result.match && result.changed_documents.map((d) => (
          <span key={d.document_id} className="mono" style={{ fontSize: 11.5, color: "var(--fail)" }}>
            {d.filename} {d.version_id ? `(${d.version_id.split("@")[1].toUpperCase()})` : ""}: {shortHash(d.committed_sha256)} → {shortHash(d.current_sha256)}
          </span>
        ))}
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
  const configured = contractConfigured();
  const [auditor, setAuditor] = useState(() => {
    try {
      return localStorage.getItem("ts-auditor") ?? "";
    } catch {
      return "";
    }
  });

  // --- Snapshot (evidence package) state -----------------------------------------------
  const [current, setCurrent] = useState<Snapshot | null>(null);
  const [result, setResult] = useState<Verification | null>(null);
  const [wallet, setWallet] = useState("");
  const [walletBusy, setWalletBusy] = useState(false);
  const [walletMessage, setWalletMessage] = useState("");
  const [dossierHash, setDossierHash] = useState("");
  const [chain, setChain] = useState<EvidenceRecord | null>(null);
  const [chainChecked, setChainChecked] = useState(false);
  const [chainError, setChainError] = useState("");
  const [chainBusy, setChainBusy] = useState(false);
  const [txHash, setTxHash] = useState("");
  const [commitStage, setCommitStage] = useState<"idle" | "wallet" | "pending">("idle");

  // --- Document version state ------------------------------------------------------------
  const [docId, setDocId] = useState(DEFAULT_DOCUMENT);
  const history = useVersions(docId);
  const [selected, setSelected] = useState<number | null>(null);
  const [vResult, setVResult] = useState<VersionVerification | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [seen, setSeen] = useState<Record<string, boolean>>({});
  const [notes, setNotes] = useState("");
  const [deciding, setDeciding] = useState<ReviewDecision | null>(null);
  const [versionCommit, setVersionCommit] = useState<{ caseId: string; stage: "wallet" | "pending" } | null>(null);
  const [versionTx, setVersionTx] = useState<Record<string, string>>({});
  const upload = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      localStorage.setItem("ts-auditor", auditor);
    } catch {
      /* storage disabled */
    }
  }, [auditor]);

  useEffect(() => {
    if (!snapshots.data) return;
    // Reloading the demo replaces the snapshot list; drop a selection that no longer exists.
    if (current && !snapshots.data.some((s) => s.snapshot_id === current.snapshot_id)) {
      setCurrent(snapshots.data.at(-1) ?? null);
      setResult(null);
    } else if (!current && snapshots.data.length) setCurrent(snapshots.data[snapshots.data.length - 1]);
  }, [snapshots.data, current]);
  // Snapshot list rows are summaries; fetch the full record (component hashes, chain payload) once selected.
  useEffect(() => {
    if (!current || current.chain_payload) return;
    let active = true;
    api.snapshot(current.snapshot_id).then((snapshot) => { if (active) setCurrent(snapshot); }).catch(() => undefined);
    return () => { active = false; };
  }, [current]);
  useEffect(() => {
    let active = true;
    setChain(null);
    setChainChecked(false);
    setChainError("");
    setTxHash("");
    if (!current || !configured) return;
    setTxHash(readTx(current.snapshot_id));
    getEvidence(current.snapshot_id).then((record) => {
      if (active) { setChain(record); setChainChecked(true); }
    }).catch((error) => { if (active) setChainError(walletError(error)); });
    return () => { active = false; };
  }, [current?.snapshot_id, configured]);

  // Keep a valid version selected (latest by default; reset when the demo is reloaded).
  const versions = history.data?.versions ?? [];
  useEffect(() => {
    if (!history.data) return;
    if (selected === null || !history.data.versions.some((v) => v.version === selected)) {
      setSelected(history.data.latest_version);
      setVResult(null);
    }
  }, [history.data, selected]);

  // MST records for every sealed version (read-only RPC; one record per version, never overwritten).
  const sealed = versions.filter((v) => v.chain_payload);
  const mst = useQueries({
    queries: sealed.map((v) => ({
      queryKey: ["mst", v.chain_payload!.case_id],
      queryFn: () => getEvidence(v.chain_payload!.case_id),
      enabled: configured,
      retry: false,
      staleTime: 30_000,
    })),
  });
  const records: Record<string, EvidenceRecord | null | undefined> = {};
  sealed.forEach((v, i) => { records[v.chain_payload!.case_id] = mst[i]?.data; });
  const recordFor = (v?: DocumentVersion | null) => (v?.chain_payload ? records[v.chain_payload.case_id] : null);

  const sel = versions.find((v) => v.version === selected) ?? null;
  const selResult = vResult && vResult.document_id === docId && vResult.version === selected ? vResult : null;
  const newest = versions.length > 1 ? versions[versions.length - 1] : null;
  const reviewN = sel && sel.version > 1 ? sel.version : newest?.version ?? null;
  const explain = useVersionExplanation(docId, reviewN);
  const reviewVersion = versions.find((v) => v.version === reviewN) ?? null;

  function selectVersion(n: number) {
    setSelected(n);
    setVResult(null);
  }

  async function verifyVersion(n: number) {
    setVerifying(true);
    try {
      const r = await api.verifyVersion(docId, n);
      setSelected(n);
      setVResult(r);
      if (r.version === 1 && (r.status === "INTEGRITY_VERIFIED" || r.status === "HISTORICALLY_VERIFIED")) setSeen((s) => ({ ...s, [`${docId}:v1ok`]: true }));
      if (r.status === "INTEGRITY_MISMATCH") setSeen((s) => ({ ...s, [`${docId}:mismatch`]: true }));
      if (r.chain_payload) qc.invalidateQueries({ queryKey: ["mst", r.chain_payload.case_id] });
    } catch (error) {
      toast(<span>Verification failed: {String(error)}</span>);
    } finally {
      setVerifying(false);
    }
  }

  const refreshVersions = () => Promise.all([
    qc.invalidateQueries({ queryKey: ["versions", docId] }),
    qc.invalidateQueries({ queryKey: ["audit", TID] }),
  ]);

  // Scenario 1: edit the committed V1 file in place (no new version).
  const tamper = useMutation({
    mutationFn: () => api.tamper(docId),
    onSuccess: async (r) => {
      toast(<span>{r.change} in <b>{r.filename}</b> (V1 edited in place)</span>);
      await verifyVersion(1);
    },
    onError: (error) => toast(<span>Could not modify the document: {String(error)}</span>),
  });
  const restore = useMutation({
    mutationFn: api.restore,
    onSuccess: async (r) => {
      toast(<span>Restored {r.restored.length} document(s)</span>);
      if (selected) await verifyVersion(selected);
    },
    onError: (error) => toast(<span>Could not restore documents: {String(error)}</span>),
  });
  // Scenario 2: the bidder uploads a renewed document as V2.
  const newVersion = useMutation({
    mutationFn: () => api.demoNewVersion(docId),
    onSuccess: async (r) => {
      await refreshVersions();
      toast(<span>{r.version.label} uploaded by {r.version.created_by}</span>);
      await verifyVersion(r.version.version);
    },
    onError: async (error) => {
      toast(<span>{error instanceof ApiError ? error.message : String(error)}</span>);
      if (error instanceof ApiError && error.status === 409 && history.data?.latest_version) await verifyVersion(history.data.latest_version);
    },
  });
  const uploadVersion = useMutation({
    mutationFn: (file: File) => api.uploadVersion(docId, file, auditor.trim() ? `${auditor.trim()} (manual upload)` : "Manual upload"),
    onSuccess: async (r) => {
      await refreshVersions();
      toast(<span>{r.version.label} created · {shortHash(r.version.sha256, 4)}</span>);
      await verifyVersion(r.version.version);
    },
    onError: (error) => toast(<span>Upload failed: {error instanceof ApiError ? error.message : String(error)}</span>),
  });

  async function decide(decision: ReviewDecision) {
    if (!reviewVersion) return;
    setDeciding(decision);
    try {
      const r = await api.reviewVersion(docId, reviewVersion.version, decision, auditor, notes);
      setNotes("");
      if (r.snapshot) {
        qc.setQueryData<Snapshot[]>(["snapshots", TID], (old) => [...(old ?? []), r.snapshot!]);
        setCurrent(r.snapshot);
        setResult(null);
      }
      await Promise.all([refreshVersions(), qc.invalidateQueries({ queryKey: ["snapshots"] })]);
      toast(<span>{humanize(decision)} recorded in the audit chain (entry #{r.audit_entry.entry_id})</span>);
      if (decision === "ACCEPT") await verifyVersion(reviewVersion.version);
    } catch (error) {
      toast(<span>Could not record the decision: {error instanceof ApiError ? error.message : String(error)}</span>);
    } finally {
      setDeciding(null);
    }
  }

  async function commitVersion(v: DocumentVersion) {
    if (!v.chain_payload) return;
    const caseId = v.chain_payload.case_id;
    setWalletMessage("");
    setVersionCommit({ caseId, stage: "wallet" });
    try {
      const committed = await commitEvidenceToBlockchain(v.chain_payload, "", (hash) => {
        setVersionTx((t) => ({ ...t, [caseId]: hash }));
        setVersionCommit({ caseId, stage: "pending" });
      });
      setWallet(committed.auditor);
      setVersionTx((t) => ({ ...t, [caseId]: committed.transactionHash }));
      writeTx(caseId, committed.transactionHash);
      toast(<span>{v.label} anchored on MST Testnet as its own record</span>);
      await qc.invalidateQueries({ queryKey: ["mst", caseId] });
    } catch (error) {
      setWalletMessage(walletError(error));
    } finally {
      setVersionCommit(null);
    }
  }

  const finalize = useMutation({
    mutationFn: () => api.finalize(TID, auditor),
    onSuccess: (s) => {
      // Add the new snapshot to the cached list first so the selection check above keeps it.
      qc.setQueryData<Snapshot[]>(["snapshots", TID], (old) => [...(old ?? []), s]);
      setCurrent(s);
      setResult(null);
      toast(
        <span>
          Evidence sealed · <span className="mono">{shortHash(s.bundle_hash, 4)}</span>
        </span>,
      );
      return Promise.all([qc.invalidateQueries({ queryKey: ["snapshots"] }), qc.invalidateQueries({ queryKey: ["versions"] }), qc.invalidateQueries({ queryKey: ["audit", TID] })]);
    },
  });
  const verify = useMutation({
    mutationFn: (sid: string) => api.verify(sid),
    onSuccess: setResult,
  });
  async function verifySnapshot() {
    if (!current) return;
    verify.mutate(current.snapshot_id);
    if (configured) {
      setChainBusy(true);
      setChainError("");
      try { setChain(await getEvidence(current.snapshot_id)); setChainChecked(true); }
      catch (error) { setChainError(walletError(error)); setChainChecked(false); }
      finally { setChainBusy(false); }
    }
  }

  async function connect() {
    setWalletBusy(true);
    setWalletMessage("");
    try { setWallet((await connectWallet()).address); }
    catch (error) { setWalletMessage(walletError(error)); }
    finally { setWalletBusy(false); }
  }

  async function commitSnapshot() {
    if (!current?.chain_payload) return;
    setWalletMessage("");
    setCommitStage("wallet");
    try {
      const committed = await commitEvidenceToBlockchain(current.chain_payload, dossierHash, (hash) => { setTxHash(hash); setCommitStage("pending"); });
      setWallet(committed.auditor);
      setTxHash(committed.transactionHash);
      writeTx(current.snapshot_id, committed.transactionHash);
      setResult(null);
      toast("Evidence snapshot committed on MST Testnet");
      try { setChain(await getEvidence(current.snapshot_id)); setChainChecked(true); }
      catch (error) { setChainError(walletError(error)); }
    } catch (error) { setWalletMessage(walletError(error)); }
    finally { setCommitStage("idle"); }
  }

  if (tender.isLoading) return <LoadingBlock rows={6} />;
  if (tender.error) return isNotLoaded(tender.error) ? <NotLoaded what="evidence" /> : <ErrorCard error={tender.error} />;
  const docs = [...tender.data!.documents].sort((a, b) => Number(b.kind === "compliance") - Number(a.kind === "compliance") || a.document_id.localeCompare(b.document_id));
  const docKind = docs.find((d) => d.document_id === docId)?.kind;
  const payload = current?.chain_payload;

  // --- The seven-step story --------------------------------------------------------------
  const v1 = versions.find((v) => v.version === 1);
  const anchored = (v?: DocumentVersion | null) => !!v?.chain_payload && (configured ? chainMatches(v, recordFor(v)) : true);
  const decided = !!newest && !OPEN_STATUSES.includes(newest.status);
  const steps: StoryStep[] = [
    { title: "V1 anchored", sub: configured ? "V1 SHA-256 committed on MST" : "V1 sealed (MST not configured)", state: anchored(v1) ? "done" : "todo" },
    { title: "V1 verified", sub: "Stored file matches its fingerprint", state: seen[`${docId}:v1ok`] ? "done" : "todo" },
    { title: "Edited V1 → mismatch", sub: "Scenario 1: changed in place, no new version", state: seen[`${docId}:mismatch`] ? "bad" : "todo" },
    { title: "V2 = new version", sub: "Scenario 2: renewal uploaded, not fraud", state: newest ? "done" : "todo" },
    { title: "Change explained", sub: "Diff → rule check → explanation", state: explain.data ? "done" : "todo" },
    { title: "Auditor decides", sub: "Accept · verify · investigate", state: decided ? "done" : "todo" },
    { title: `${newest?.label ?? "V2"} anchored`, sub: "Separate MST record; V1 kept", state: newest && anchored(newest) ? "done" : "todo" },
  ];

  const selRecord = recordFor(sel);
  const selOnChain = !!sel && chainMatches(sel, selRecord);
  const selTx = sel?.chain_payload ? versionTx[sel.chain_payload.case_id] || readTx(sel.chain_payload.case_id) : "";
  const committingSel = !!sel?.chain_payload && versionCommit?.caseId === sel.chain_payload.case_id;

  return (
    <>
      <PageHead
        eyebrow="Evidence versioning + verification"
        title="Evidence integrity"
        sub="A changed hash is a fact, not a verdict. Committed versions never change; a legitimate update is a new version with its own fingerprint, explained and decided by an auditor, and anchored on MST as a separate record."
        actions={
          <a className="btn" href={api.dossierUrl(TID)} target="_blank" rel="noreferrer">
            <Download size={15} /> Dossier data (JSON)
          </a>
        }
      />

      <div style={{ marginBottom: 18 }}>
        <StoryRail steps={steps} />
      </div>

      <div className="grid grid--main-side">
        <div className="stack" style={{ gap: 18 }}>
          <VersionSeal version={sel} result={selResult} record={selRecord}>
            <div className="row" style={{ marginTop: 10, flexWrap: "wrap" }}>
              <Button variant="primary" size="lg" icon={<Fingerprint size={16} />} disabled={!sel} loading={verifying} onClick={() => sel && verifyVersion(sel.version)}>
                Verify {sel?.label ?? "version"}
              </Button>
              {sel?.chain_payload && configured && !selOnChain && selRecord !== undefined && selResult?.status !== "INTEGRITY_MISMATCH" && (
                <Button variant="brand" icon={<Anchor size={15} />} loading={committingSel} disabled={!!versionCommit} onClick={() => commitVersion(sel)}>
                  {committingSel ? (versionCommit?.stage === "pending" ? "Transaction pending" : "Waiting for BridgeKey") : `Anchor ${sel.label} on MST`}
                </Button>
              )}
              {selOnChain && <Badge tone="pass">{sel!.label} anchored on MST</Badge>}
              {sel && !sel.chain_payload && (
                <span className="muted" style={{ fontSize: 12.5 }}>
                  {OPEN_STATUSES.includes(sel.status) ? `${sel.label} can be anchored after an auditor accepts it.` : `${sel.label} is anchored when evidence is next finalised.`}
                </span>
              )}
            </div>
          </VersionSeal>

          <Card
            title={`Document history · ${history.data?.filename ?? docId}`}
            icon={<History size={15} />}
            flush
            actions={
              <>
                <select className="select" value={docId} onChange={(e) => { setDocId(e.target.value); setSelected(null); setVResult(null); }} aria-label="Document">
                  {docs.map((d) => (
                    <option key={d.document_id} value={d.document_id}>
                      {d.filename}
                    </option>
                  ))}
                </select>
                <Button size="sm" icon={<Upload size={13} />} loading={uploadVersion.isPending} onClick={() => upload.current?.click()} title="Upload a new version (PDF)">
                  New version
                </Button>
                <input ref={upload} type="file" accept="application/pdf" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadVersion.mutate(f); e.target.value = ""; }} />
              </>
            }
          >
            {history.isLoading && <p className="muted" style={{ padding: 16 }}>Loading versions…</p>}
            {!!history.error && <div style={{ padding: 16 }}><Callout tone="danger">{String(history.error)}</Callout></div>}
            {versions.length > 0 && <VersionTable versions={versions} selected={selected} onSelect={selectVersion} records={records} configured={configured} />}
            {sel && (
              <div style={{ padding: 16, borderTop: "1px solid var(--line)" }}>
                <VersionDetails version={sel} txHash={selTx} />
              </div>
            )}
          </Card>

          {reviewN && (
            <ChangeReviewCard docId={docId} comparison={explain.data?.comparison} explanation={explain.data?.explanation} loading={explain.isLoading} error={explain.error}>
              {reviewVersion && <ReviewActions version={reviewVersion} auditor={auditor} onAuditor={setAuditor} notes={notes} onNotes={setNotes} busy={deciding} onDecide={decide} />}
            </ChangeReviewCard>
          )}

          <Card title="Evidence package (snapshot)" icon={<Stamp size={15} />}>
            <div className="stack">
              <p className="dim" style={{ fontSize: 13, margin: 0 }}>
                A snapshot freezes the rulebook, compliance results, findings, audit trail and the fingerprint of each document version into one SHA-256. Verifying an old snapshot re-checks the versions it committed, so a later V2 is reported as a new version, not a mismatch.
              </p>
              <Seal result={result} snapshot={current} chain={chain} chainChecked={chainChecked} />
              {verify.isError && <Callout tone="danger">Verification failed: {String(verify.error)}</Callout>}
              {chainError && <Callout tone="danger">MST Testnet read failed: {chainError}</Callout>}
              <div className="row" style={{ flexWrap: "wrap" }}>
                <Button icon={<Fingerprint size={15} />} disabled={!current} loading={verify.isPending || chainBusy} onClick={verifySnapshot}>
                  Verify snapshot
                </Button>
                {payload && configured && (
                  <Button variant="brand" icon={<Anchor size={15} />} disabled={!!chain} loading={commitStage !== "idle"} onClick={commitSnapshot}>
                    {commitStage === "wallet" ? "Waiting for BridgeKey" : commitStage === "pending" ? "Transaction pending" : chain ? "Snapshot on MST" : "Commit snapshot on MST"}
                  </Button>
                )}
                {txHash && (
                  <a className="row mono" href={`${MST_TESTNET_EXPLORER}/tx/${txHash}`} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
                    <ExternalLink size={13} /> {shortHash(txHash, 6)}
                  </a>
                )}
              </div>
              <div className="row" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
                <div className="field" style={{ flex: "1 1 180px" }}>
                  <label htmlFor="fin-auditor">Auditor</label>
                  <input id="fin-auditor" className="input" value={auditor} onChange={(e) => setAuditor(e.target.value)} placeholder="Your name" />
                </div>
                <Button variant="brand" icon={<Stamp size={15} />} disabled={!auditor.trim()} loading={finalize.isPending} onClick={() => finalize.mutate()}>
                  Finalise &amp; seal evidence
                </Button>
              </div>
              {finalize.isError && <Callout tone="danger">{String(finalize.error)}</Callout>}

              <details className="disclosure">
                <summary>
                  <ChevronRight size={14} className="disclosure__chev" />
                  Snapshot details
                  <span className="muted" style={{ fontWeight: 400, marginLeft: "auto", fontSize: 12 }}>
                    {snapshots.data?.length ?? 0} snapshot(s)
                  </span>
                </summary>
                <div className="stack stack--sm" style={{ padding: 12 }}>
                  {snapshots.data && snapshots.data.length > 1 && (
                    <div className="row" style={{ flexWrap: "wrap" }}>
                      {snapshots.data.map((s) => (
                        <button key={s.snapshot_id} className={`btn btn--sm${current?.snapshot_id === s.snapshot_id ? " btn--primary" : ""}`} onClick={() => { setCurrent(s); setResult(null); }}>
                          <span className="mono">{s.snapshot_id}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {current?.component_hashes && (
                    <table className="table">
                      <tbody>
                        {Object.entries(current.component_hashes).map(([k, v]) => (
                          <tr key={k}>
                            <td style={{ width: 130 }}>{humanize(k)}</td>
                            <td className="hash" style={{ fontSize: 11 }}>{v}</td>
                            <td style={{ width: 80 }}>{result && (result.changed_components.includes(k) ? <Badge tone="fail">changed</Badge> : <Badge tone="pass">intact</Badge>)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  {payload && (
                    <>
                      <div className="field">
                        <label htmlFor="dossier-hash">Dossier PDF SHA-256 (optional, snapshot commit only)</label>
                        <input id="dossier-hash" className="input mono" value={dossierHash} onChange={(e) => setDossierHash(e.target.value.trim())} placeholder="64 hex characters; empty means no PDF" />
                      </div>
                      <div className="row row--between">
                        <span className="section-label">On-chain payload</span>
                        <Button size="sm" icon={<Copy size={13} />} onClick={() => navigator.clipboard?.writeText(JSON.stringify(payload, null, 2)).then(() => toast("Chain payload copied"))}>
                          Copy
                        </Button>
                      </div>
                      <pre className="code" style={{ margin: 0, fontSize: 11.5, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>{JSON.stringify(payload, null, 2)}</pre>
                    </>
                  )}
                </div>
              </details>
            </div>
          </Card>
        </div>

        <div className="stack" style={{ gap: 18 }}>
          <Card title="Demo scenarios" icon={<FilePen size={15} />}>
            <div className="stack">
              <div className="stack stack--sm">
                <span className="section-label">Scenario 1 · integrity mismatch</span>
                <p className="dim" style={{ fontSize: 12.5, margin: 0 }}>Someone edits the committed V1 file in place, without creating a version.</p>
                <div className="row">
                  <Button variant="danger" icon={<FilePen size={15} />} loading={tamper.isPending} onClick={() => tamper.mutate()}>
                    Edit V1 in place
                  </Button>
                  <Button icon={<RotateCcw size={15} />} loading={restore.isPending} onClick={() => restore.mutate()}>
                    Restore
                  </Button>
                </div>
              </div>
              <hr className="divider" style={{ margin: 0 }} />
              <div className="stack stack--sm">
                <span className="section-label">Scenario 2 · new version</span>
                <p className="dim" style={{ fontSize: 12.5, margin: 0 }}>Five months later the bidder uploads renewed certificates as V2. V1 stays untouched.</p>
                <Button variant="brand" icon={<FilePlus2 size={15} />} loading={newVersion.isPending} disabled={docKind !== "compliance"} onClick={() => newVersion.mutate()}>
                  Upload renewed V2
                </Button>
                {docKind !== "compliance" && <span className="muted" style={{ fontSize: 12 }}>Pick a compliance document, or use “New version” to upload a PDF.</span>}
              </div>
              <Callout>Hashes prove what changed. They do not prove the original documents were truthful; the auditor decides.</Callout>
            </div>
          </Card>

          <Card title="Blockchain auditor" icon={<Wallet size={15} />}>
            <div className="stack stack--sm">
              <span className="muted" style={{ fontSize: 12 }}>Network · MST Testnet (91562037)</span>
              <span className="muted" style={{ fontSize: 12 }}>Wallet · <span className="mono">{wallet || "Not connected"}</span></span>
              {!configured && <Callout>Deploy the contract to MST Testnet, set <span className="mono">VITE_TENDERSHIELD_CONTRACT_ADDRESS</span> in frontend/.env.local, then restart the frontend.</Callout>}
              <div className="row">
                <Button icon={<Wallet size={15} />} loading={walletBusy} onClick={connect}>Connect BridgeKey</Button>
              </div>
              <span className="muted" style={{ fontSize: 12 }}>Each document version and each snapshot is its own record. Existing records are never overwritten.</span>
              {walletMessage && <Callout tone="danger">
                <span>{walletMessage}</span>
                {walletMessage.includes("wallet provider") || walletMessage.includes("BridgeKey was not found") ? (
                  <span> Get the <a href="https://chromewebstore.google.com/detail/bridgekey/bfjojdcfenehemjgjlepdjomkpginlkg" target="_blank" rel="noreferrer">BridgeKey Chrome extension</a>, then reopen this page in Chrome.</span>
                ) : null}
              </Callout>}
              {wallet && <a href="https://faucet.mstblockchain.com/" target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>Fund this auditor wallet with testnet MSTC if it needs transaction gas.</a>}
              {configured && <a className="row mono" href={`${MST_TESTNET_EXPLORER}/address/${TENDERSHIELD_CONTRACT_ADDRESS}`} target="_blank" rel="noreferrer" style={{ fontSize: 12, overflowWrap: "anywhere" }}><ExternalLink size={13} /> Contract {TENDERSHIELD_CONTRACT_ADDRESS}</a>}
            </div>
          </Card>

          <Card title="Audit chain" actions={audit.data && <Badge tone={audit.data.chain.valid ? "pass" : "fail"}>{audit.data.chain.valid ? "valid" : "broken"}</Badge>}>
            <div className="stack stack--sm">
              {audit.data?.entries.slice(-7).reverse().map((e) => (
                <div key={e.entry_id} className="row row--between" style={{ fontSize: 12.5 }}>
                  <span>
                    <span className="mono muted">#{e.entry_id}</span> {humanize(e.action)}
                    {typeof e.payload.decision === "string" && <span className="muted"> · {humanize(e.payload.decision)}</span>}
                  </span>
                  <span className="mono muted">{e.entry_hash.slice(0, 10)}…</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
