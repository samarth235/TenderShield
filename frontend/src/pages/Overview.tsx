import { ArrowRight, BookOpenText, FileStack, Grid3x3, History, Play, ShieldAlert, Users } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { ErrorCard } from "../components/NotLoaded";
import { Badge, Button, Card, LevelBadge, LoadingBlock, PageHead, StatTile, StatusBadge } from "../components/ui";
import { CATEGORY_LABEL, fmtCr, fmtDateTime, levelColor, prettyTitle, shortTitle } from "../lib/format";
import { isNotLoaded, useCompliance, useFindings, useLoadDemo, useRules, useTender } from "../lib/hooks";

const LIFECYCLE = ["UNDERSTAND", "VERIFY", "CONNECT", "DETECT", "EXPLAIN", "CHALLENGE", "REVIEW", "REPORT", "COMMIT", "VERIFY"];

const SCENARIOS = [
  { who: "Vendor A + Vendor B", title: "Multi-signal investigation case", body: "Shared director and premises, repeated co-bidding, rotating winners and near-identical proposals.", tone: "high" as const, result: "HIGH signal" },
  { who: "Vendor C + Vendor D", title: "Single weak relationship", body: "Shared director only. They rarely bid together and their documents differ. Noted, not escalated.", tone: "low" as const, result: "LOW" },
  { who: "Vendor E", title: "Genuine compliance failure", body: "ISO 9001 certificate expired before the bid date: a deterministic rule result.", tone: "fail" as const, result: "FAIL" },
  { who: "Vendor F", title: "Missing information", body: "Director information unavailable. Missing data is flagged, never treated as wrongdoing.", tone: "unknown" as const, result: "UNKNOWN" },
];

function Landing() {
  const load = useLoadDemo();
  return (
    <div className="stack" style={{ gap: 22 }}>
      <section className="hero">
        <div className="stack" style={{ position: "relative", gap: 16 }}>
          <Badge tone="brand">Explainable tender assurance</Badge>
          <h1>Turn fragmented procurement records into evidence you can defend.</h1>
          <p>
            TenderShield reads the tender, checks every bidder against every requirement, and connects vendors,
            directors, addresses and bidding history into a relationship graph. Each finding is explained, stress-tested
            by removing evidence, decided by a human auditor, and sealed with a cryptographic hash.
          </p>
          <div className="row" style={{ marginTop: 6 }}>
            <Button variant="brand" size="lg" icon={<Play size={16} />} loading={load.isPending} onClick={() => load.mutate()}>
              Load demonstration tender
            </Button>
            <span className="dim" style={{ fontSize: 13 }}>TN-2026-014 · 6 bidders · 480 historical tenders · runs offline</span>
          </div>
          {load.isError && <p style={{ color: "var(--fail)" }}>{String(load.error)} — is the API running (`make run`)?</p>}
          <div className="lifecycle">
            {LIFECYCLE.map((s, i) => (
              <span key={i}>{s}</span>
            ))}
          </div>
        </div>
      </section>
      <div>
        <div className="section-label" style={{ marginBottom: 10 }}>
          Planted scenarios in the demonstration dataset
        </div>
        <div className="grid grid--4">
          {SCENARIOS.map((s) => (
            <div key={s.who} className="card scenario">
              <div className="row row--between">
                <span className="scenario__who">{s.who}</span>
                <Badge tone={s.tone} dot>
                  {s.result}
                </Badge>
              </div>
              <h3 style={{ fontSize: 15 }}>{s.title}</h3>
              <p className="dim" style={{ fontSize: 13 }}>
                {s.body}
              </p>
            </div>
          ))}
        </div>
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
        eyebrow={`Tender ${t.tender_id} · Overview`}
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
