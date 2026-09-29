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
  Wallet,
  ExternalLink,
} from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Snapshot, Verification } from "../api/types";
import { MST_TESTNET_EXPLORER, TENDERSHIELD_CONTRACT_ADDRESS } from "../blockchain/config";
import { commitEvidenceToBlockchain, connectWallet, contractConfigured, getEvidence, walletError, type EvidenceRecord } from "../blockchain/wallet";
import { ErrorCard, NotLoaded } from "../components/NotLoaded";
import { Badge, Button, Callout, Card, LoadingBlock, PageHead, useToast } from "../components/ui";
import { fmtDateTime, humanize, shortHash } from "../lib/format";
import { isNotLoaded, TID, useAuditLog, useSnapshots, useTender } from "../lib/hooks";

function Seal({ result, snapshot, chain, chainChecked }: { result: Verification | null; snapshot: Snapshot | null; chain: EvidenceRecord | null; chainChecked: boolean }) {
  const chainMatch = !!result && !!chain && chain.caseId === snapshot?.snapshot_id && chain.tenderId === snapshot?.tender_id && chain.evidenceHash.toLowerCase() === `0x${result.current_hash}`.toLowerCase() && chain.evidenceHash.toLowerCase() === `0x${snapshot?.bundle_hash}`.toLowerCase() && (!snapshot?.chain_payload || chain.auditHeadHash.toLowerCase() === `0x${snapshot.chain_payload.audit_head_hash}`.toLowerCase());
  const state = !result ? "idle" : chain && !chainMatch ? "bad" : !result.match ? "bad" : chainMatch ? "ok" : "idle";
  const Icon = state === "ok" ? ShieldCheck : state === "bad" ? ShieldX : Lock;
  return (
    <div className={`seal seal--${state}`} key={result?.verified_at ?? "idle"}>
      <div className="seal__icon">
        <Icon size={44} strokeWidth={1.6} />
      </div>
      <div className="stack stack--sm" style={{ minWidth: 0 }}>
        <span className="section-label">{result ? `Checked ${fmtDateTime(result.verified_at)}` : snapshot ? "Evidence snapshot finalised" : "No evidence snapshot yet"}</span>
        <span className="seal__status" style={{ color: state === "ok" ? "var(--pass)" : state === "bad" ? "var(--fail)" : "var(--ink)" }}>
          {state === "ok" ? "✓ Blockchain integrity verified" : state === "bad" ? "✗ Integrity mismatch" : result?.match ? chainChecked ? "Backend hash verified · awaiting blockchain commitment" : "Backend hash verified · blockchain unavailable" : snapshot ? "Ready to verify" : "Finalise evidence to seal it"}
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

  useEffect(() => {
    if (!current && snapshots.data?.length) setCurrent(snapshots.data[snapshots.data.length - 1]);
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
    if (!current || !contractConfigured()) return;
    try { setTxHash(localStorage.getItem(`ts-mst-tx:${TENDERSHIELD_CONTRACT_ADDRESS}:${current.snapshot_id}`) ?? ""); } catch { /* storage disabled */ }
    getEvidence(current.snapshot_id).then((record) => {
      if (active) { setChain(record); setChainChecked(true); }
    }).catch((error) => { if (active) setChainError(walletError(error)); });
    return () => { active = false; };
  }, [current?.snapshot_id]);

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
  async function verifyIntegrity() {
    if (!current) return;
    verify.mutate(current.snapshot_id);
    if (contractConfigured()) {
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

  async function commit() {
    if (!current?.chain_payload) return;
    setWalletMessage("");
    setCommitStage("wallet");
    try {
      const committed = await commitEvidenceToBlockchain(current.chain_payload, dossierHash, (hash) => { setTxHash(hash); setCommitStage("pending"); });
      setWallet(committed.auditor);
      setTxHash(committed.transactionHash);
      try { localStorage.setItem(`ts-mst-tx:${TENDERSHIELD_CONTRACT_ADDRESS}:${current.snapshot_id}`, committed.transactionHash); } catch { /* storage disabled */ }
      setResult(null);
      toast("Evidence committed on MST Testnet");
      try { setChain(await getEvidence(current.snapshot_id)); setChainChecked(true); }
      catch (error) { setChainError(walletError(error)); }
    } catch (error) { setWalletMessage(walletError(error)); }
    finally { setCommitStage("idle"); }
  }
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
    { done: !!chain, title: "Commit the hash on-chain", body: "BridgeKey signs the snapshot and audit hashes on MST Testnet." },
    { done: !!result && !!chain && result.match && chain.evidenceHash.toLowerCase() === `0x${result.current_hash}`.toLowerCase(), title: "Verify at any later time", body: "Compare the current backend hash with the immutable MST Testnet record." },
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
          <Seal result={result} snapshot={current} chain={chain} chainChecked={chainChecked} />

          <div className="row">
            <Button variant="primary" size="lg" icon={<Fingerprint size={16} />} disabled={!current} loading={verify.isPending || chainBusy} onClick={verifyIntegrity}>
              Verify integrity
            </Button>
            {current && (
              <span className="muted" style={{ fontSize: 13 }}>
                Snapshot <span className="mono">{current.snapshot_id}</span> · {fmtDateTime(current.created_at)}
              </span>
            )}
          </div>
          {chainError && <Callout tone="danger">MST Testnet read failed: {chainError}</Callout>}

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
          <Card title="Blockchain auditor" icon={<Wallet size={15} />}>
            <div className="stack stack--sm">
              <span className="muted" style={{ fontSize: 12 }}>Network · MST Testnet (91562037)</span>
              <span className="muted" style={{ fontSize: 12 }}>Wallet · <span className="mono">{wallet || "Not connected"}</span></span>
              {!contractConfigured() && <Callout>Deploy the contract to MST Testnet, set <span className="mono">VITE_TENDERSHIELD_CONTRACT_ADDRESS</span> in frontend/.env.local, then restart the frontend.</Callout>}
              <div className="row">
                <Button icon={<Wallet size={15} />} loading={walletBusy} onClick={connect}>Connect BridgeKey</Button>
              </div>
              {payload && <>
                <div className="field">
                  <label htmlFor="dossier-hash">Dossier PDF SHA-256 (optional)</label>
                  <input id="dossier-hash" className="input mono" value={dossierHash} onChange={(e) => setDossierHash(e.target.value.trim())} placeholder="64 hex characters; empty means no PDF" />
                </div>
                <Button variant="brand" disabled={!wallet || !contractConfigured() || !!chain} loading={commitStage !== "idle"} onClick={commit}>
                  {commitStage === "wallet" ? "Waiting for BridgeKey" : commitStage === "pending" ? "Transaction pending" : chain ? "Already committed" : "Commit evidence"}
                </Button>
              </>}
              {walletMessage && <Callout tone="danger">
                <span>{walletMessage}</span>
                {walletMessage.includes("wallet provider") || walletMessage.includes("BridgeKey was not found") ? (
                  <span> Get the <a href="https://chromewebstore.google.com/detail/bridgekey/bfjojdcfenehemjgjlepdjomkpginlkg" target="_blank" rel="noreferrer">BridgeKey Chrome extension</a>, then reopen this page in Chrome.</span>
                ) : null}
              </Callout>}
              {chain && <>
                <Badge tone="pass">Evidence committed</Badge>
                <span className="muted" style={{ fontSize: 12 }}>Auditor · <span className="mono">{chain.auditor}</span></span>
                <span className="muted" style={{ fontSize: 12 }}>Recorded · {fmtDateTime(new Date(Number(chain.recordedAt) * 1000).toISOString())}</span>
                <span className="muted" style={{ fontSize: 12 }}>Evidence hash · <span className="hash">{chain.evidenceHash}</span></span>
              </>}
              {txHash && <a className="row mono" href={`${MST_TESTNET_EXPLORER}/tx/${txHash}`} target="_blank" rel="noreferrer" style={{ fontSize: 12, overflowWrap: "anywhere" }}><ExternalLink size={13} /> Transaction {txHash}</a>}
              {wallet && <a href="https://faucet.mstblockchain.com/" target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>Fund this auditor wallet with testnet MSTC if it needs transaction gas.</a>}
              {contractConfigured() && <a className="row mono" href={`${MST_TESTNET_EXPLORER}/address/${TENDERSHIELD_CONTRACT_ADDRESS}`} target="_blank" rel="noreferrer" style={{ fontSize: 12, overflowWrap: "anywhere" }}><ExternalLink size={13} /> Contract {TENDERSHIELD_CONTRACT_ADDRESS}</a>}
            </div>
          </Card>
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
