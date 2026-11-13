import { ArrowRight, BookOpenText, FileStack, Grid3x3, History, ShieldAlert, Upload, Users } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ErrorCard } from "../components/NotLoaded";
import { Badge, Button, Callout, Card, LevelBadge, LoadingBlock, PageHead, StatTile, StatusBadge } from "../components/ui";
import { CATEGORY_LABEL, fmtCr, fmtDateTime, levelColor, prettyTitle, shortTitle } from "../lib/format";
import { isNotLoaded, useCompliance, useFindings, useRules, useTender, useTenders, useTid, useUploadTender } from "../lib/hooks";
import { useAuth } from "../lib/auth";
import { useCurrentTender } from "../lib/tender";

/** Shown when no tender is selected: invites a real upload. Nothing is pre-populated. */
export function Landing() {
  const upload = useUploadTender();
  const tenders = useTenders();
  const { setTid } = useCurrentTender();
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [department, setDepartment] = useState("");
  const { can } = useAuth();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    upload.mutate(
      { file, title: title.trim() || undefined, department: department.trim() || undefined },
      { onSuccess: () => navigate("/restructuring") },
    );
  };

  return (
    <div className="stack" style={{ gap: 22 }}>
      <section className="hero">
        <div className="stack" style={{ position: "relative", gap: 16 }}>
          <Badge tone="brand">SDG 9.3 procurement restructuring</Badge>
          <h1>Open large public tenders to small and medium enterprises.</h1>
          <p>
            Upload a real tender document. TenderShield extracts its scope, maps the technical dependencies between
            work items, proposes procurement packages, finds suppliers with published evidence of capability, and screens
            them for relationships that need review. Every recommendation cites its source and is decided by an officer.
          </p>
        </div>
      </section>

      <div className="grid grid--main-side">
        <Card title="Upload a tender" icon={<Upload size={15} />}>
          {!can("officer") ? (
            <p className="dim" style={{ fontSize: 13 }}>Your account is read-only. A procurement officer uploads tenders.</p>
          ) : (
          <form className="stack" onSubmit={submit}>
            <div className="field">
              <label htmlFor="tender-file">Tender document (PDF, digital text)</label>
              <input id="tender-file" className="input" type="file" accept="application/pdf,.pdf" required
                onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </div>
            <div className="field">
              <label htmlFor="tender-title">Title (optional, read from the document if blank)</label>
              <input id="tender-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="tender-dept">Procuring department (optional)</label>
              <input id="tender-dept" className="input" value={department} onChange={(e) => setDepartment(e.target.value)} />
            </div>
            <div className="row">
              <Button variant="brand" icon={<Upload size={15} />} loading={upload.isPending} disabled={!file}>
                Upload and extract
              </Button>
            </div>
            {upload.isError && <Callout tone="danger">{upload.error instanceof Error ? upload.error.message : String(upload.error)}</Callout>}
          </form>
          )}
        </Card>

        <Card title="Existing tenders" icon={<FileStack size={15} />} flush>
          {tenders.isLoading && <div className="card__body"><LoadingBlock rows={2} /></div>}
          {tenders.isError && <div className="card__body"><ErrorCard error={tenders.error} /></div>}
          {tenders.data?.length === 0 && (
            <div className="card__body dim" style={{ fontSize: 13 }}>No tenders uploaded yet.</div>
          )}
          {tenders.data?.map((t) => (
            <button key={t.tender_id} type="button" className="finding-row" style={{ width: "100%", textAlign: "left", background: "none", border: 0 }}
              onClick={() => { setTid(t.tender_id); navigate("/restructuring"); }}>
              <span className="finding-row__rail" />
              <div>
                <div className="finding-row__title">{shortTitle(t.title)}</div>
                <div className="finding-row__meta"><span className="mono">{t.tender_id}</span><span>{t.department}</span></div>
              </div>
              <ArrowRight size={14} />
            </button>
          ))}
        </Card>
      </div>
    </div>
  );
}

export function Overview() {
  const tender = useTender();
  const rules = useRules();
  const compliance = useCompliance();
  const findings = useFindings();
  const navigate = useNavigate();
  const TID = useTid();

  if (!TID) return <Landing />;
  if (tender.isLoading) return <LoadingBlock rows={6} />;
  if (tender.error && isNotLoaded(tender.error)) return <Landing />;
  if (tender.error) return <ErrorCard error={tender.error} />;
  const t = tender.data!;

  const counts = compliance.data?.vendors.reduce(
    (acc, v) => {
      acc.fail += v.counts.FAIL;
      acc.unknown += v.counts.UNKNOWN;
      return acc;
    },
    { fail: 0, unknown: 0 },
  );
  const escalated = findings.data?.filter((f) => f.category === "INVESTIGATION_SIGNAL" && ["HIGH", "MEDIUM"].includes(f.level)) ?? [];
  const statusOf = Object.fromEntries((compliance.data?.vendors ?? []).map((v) => [v.vendor_id, v.status]));
  const involvement = (vid: string) =>
    findings.data?.filter((f) => f.subject.vendors.some((v) => v.vendor_id === vid) && f.recommendation !== "NO_ACTION") ?? [];

  return (
    <>
      <PageHead
        eyebrow={`Tender ${t.tender_id} · Assurance overview`}
        title={shortTitle(t.title)}
        sub={
          <>
            {t.department} · Estimated value {fmtCr(t.estimated_value_cr)} · Bid deadline {fmtDateTime(t.bid_deadline)}
          </>
        }
      />

      <div className="grid grid--4">
        <StatTile icon={<Users size={14} />} label="Bidders" value={t.bidders.length} hint={<><FileStack size={12} style={{ verticalAlign: -2 }} /> {t.documents.length} documents ingested</>} />
        <StatTile
          icon={<BookOpenText size={14} />}
          label="Requirements extracted"
          value={rules.data?.rules.length ?? "—"}
          hint={rules.data ? `${rules.data.rules.filter((r) => r.mandatory).length} mandatory · ${rules.data.method} extractor` : undefined}
        />
        <StatTile
          icon={<Grid3x3 size={14} />}
          label="Compliance checks"
          value={compliance.data?.evaluations ?? "—"}
          hint={counts ? `${counts.fail} fail · ${counts.unknown} insufficient data` : undefined}
        />
        <StatTile
          icon={<ShieldAlert size={14} />}
          label="Escalated signals"
          value={escalated.length}
          accent={escalated.length ? "var(--high)" : undefined}
          hint={<><History size={12} style={{ verticalAlign: -2 }} /> {t.historical_tenders_available} historical tenders analysed</>}
        />
      </div>

      <div className="grid grid--overview">
        <Card
          title="Findings requiring attention"
          icon={<ShieldAlert size={15} />}
          flush
          actions={
            <Link to="/findings" className="row" style={{ gap: 4, fontSize: 13 }}>
              All findings <ArrowRight size={14} />
            </Link>
          }
        >
          {findings.isLoading && (
            <div className="card__body">
              <LoadingBlock />
            </div>
          )}
          {findings.data?.map((f) => (
            <Link key={f.finding_id} to={`/findings/${f.finding_id}`} className="finding-row">
              <span className={`finding-row__rail rail--${f.level}`} />
              <div>
                <div className="finding-row__title">{prettyTitle(f.title)}</div>
                <div className="finding-row__meta">
                  <span className="mono">{f.finding_id.split("-").pop()}</span>
                  <span>{CATEGORY_LABEL[f.category]}</span>
                  <span>{f.evidence_count} evidence items</span>
                </div>
              </div>
              <div className="row">
                <LevelBadge level={f.level} />
              </div>
            </Link>
          ))}
        </Card>

        <Card title="Bidders" icon={<Users size={15} />} flush>
          <table className="table">
            <thead>
              <tr>
                <th>Bidder</th>
                <th className="num">Bid amount</th>
                <th style={{ textAlign: "right" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {t.bidders.map((b) => {
                const inv = involvement(b.vendor_id);
                return (
                  <tr key={b.vendor_id} className="clickable" onClick={() => navigate(`/graph?focus=${b.vendor_id}`)}>
                    <td style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 600 }}>{b.alias}</div>
                      <div className="muted truncate" style={{ fontSize: 12 }} title={b.name}>
                        {b.name}
                      </div>
                    </td>
                    <td className="num mono nowrap">{fmtCr(b.amount_cr)}</td>
                    <td style={{ textAlign: "right" }}>
                      <div className="stack" style={{ alignItems: "flex-end", gap: 4 }}>
                        {statusOf[b.vendor_id] && <StatusBadge status={statusOf[b.vendor_id]} />}
                        {inv.length > 0 && (
                          <span className="nowrap" style={{ fontSize: 11.5, fontWeight: 500, color: levelColor(inv[0].level) }}>
                            {inv.length} finding{inv.length > 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </div>
    </>
  );
}
