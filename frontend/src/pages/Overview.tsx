import {
  ArrowRight,
  BookOpenText,
  CheckCircle2,
  FileStack,
  Grid3x3,
  History,
  Play,
  RefreshCw,
  ShieldAlert,
  Users,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { ErrorCard } from "../components/NotLoaded";
import { Badge, Button, Card, LevelBadge, LoadingBlock, PageHead, StatTile, StatusBadge } from "../components/ui";
import { CATEGORY_LABEL, fmtCr, fmtDateTime, fmtMs, levelColor, prettyTitle, STAGE_LABEL } from "../lib/format";
import {
  isNotLoaded,
  useAnalysisReport,
  useCompliance,
  useFindings,
  useLoadDemo,
  useRules,
  useRunAnalysis,
  useTender,
} from "../lib/hooks";

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
        <div className="hero__grid" />
        <div className="stack" style={{ position: "relative", gap: 16 }}>
          <Badge tone="brand">Explainable tender assurance</Badge>
          <h1>Turn fragmented procurement records into evidence you can defend.</h1>
          <p>
            TenderShield Nexus reads the tender, checks every bidder against every requirement, and connects vendors,
            directors, addresses and bidding history into a relationship graph. Each finding is explained, stress-tested
            by removing evidence, decided by a human auditor, and sealed with a cryptographic hash.
          </p>
          <div className="row" style={{ marginTop: 6 }}>
            <Button variant="brand" size="lg" icon={<Play size={16} />} loading={load.isPending} onClick={() => load.mutate()}>
              Load demonstration tender
            </Button>
            <span style={{ color: "#8d99b0", fontSize: 13 }}>TN-2026-014 · 6 bidders · 120 historical tenders · runs offline</span>
          </div>
          {load.isError && <p style={{ color: "#ffb4a8" }}>{String(load.error)} — is the API running (`make run`)?</p>}
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

function Pipeline() {
  const report = useAnalysisReport();
  const tender = useTender();
  const run = useRunAnalysis();
  const stages = report.data?.stages;
  const completed = new Set(tender.data?.completed_stages ?? []);
  const artifactFor: Record<string, string> = {
    extract_rules: "rule_extraction",
    ingest_evidence: "compliance",
    compliance: "compliance",
    entity_resolution: "entities",
    document_similarity: "similarity",
    relationship_graph: "graph",
    behaviour_analysis: "behaviour",
    reasoning: "findings",
  };
  const metric = (stage: string, s?: Record<string, unknown>): string => {
    if (!s) return completed.has(artifactFor[stage]) ? "complete" : "pending";
    switch (stage) {
      case "extract_rules":
        return `${s.rules_extracted} rules · ${s.method}`;
      case "ingest_evidence":
        return `${s.facts_extracted} facts`;
      case "compliance":
        return `${s.evaluations} checks`;
      case "entity_resolution":
        return `${s.historical_records_resolved} records linked`;
      case "document_similarity":
        return `${s.pairs} pairs · ${s.backend}`;
      case "relationship_graph":
        return `${(s.full_graph as { nodes: number }).nodes} nodes`;
      case "behaviour_analysis":
        return `${(s.model as { training_pairs?: number }).training_pairs ?? 0} pairs scored`;
      case "reasoning":
        return `${s.findings} findings`;
      default:
        return "";
    }
  };
  const order = Object.keys(STAGE_LABEL);
  return (
    <Card
      title="Analysis pipeline"
      icon={<CheckCircle2 size={15} />}
      flush
      actions={
        <>
          {report.data && <span className="muted mono" style={{ fontSize: 12 }}>total {fmtMs(report.data.duration_ms)}</span>}
          <Button size="sm" icon={<RefreshCw size={13} />} loading={run.isPending} onClick={() => run.mutate()}>
            Re-run analysis
          </Button>
        </>
      }
    >
      <div className="pipeline">
        {order.map((name, i) => {
          const st = stages?.find((x) => x.stage === name);
          const done = !!st || completed.has(artifactFor[name]);
          return (
            <div key={name} className="pipeline__step">
              {done && <span className="pipeline__bar" />}
              <span className="pipeline__num">{String(i + 1).padStart(2, "0")}</span>
              <span className="pipeline__name">{STAGE_LABEL[name]}</span>
              <span className="pipeline__metric">{metric(name, st?.summary)}</span>
              {st && <span className="pipeline__time">{fmtMs(st.duration_ms)}</span>}
            </div>
          );
        })}
      </div>
    </Card>
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
        eyebrow={`Tender ${t.tender_id}`}
        title={t.title}
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

      <Pipeline />

      <div className="grid grid--main-side">
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
                <StatusBadge status={f.status} />
                <LevelBadge level={f.level} />
              </div>
            </Link>
          ))}
        </Card>

        <Card title="Bidders" icon={<Users size={15} />} flush>
          <table className="table">
            <tbody>
              {t.bidders.map((b) => {
                const inv = involvement(b.vendor_id);
                return (
                  <tr key={b.vendor_id} className="clickable" onClick={() => navigate(`/graph?focus=${b.vendor_id}`)}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{b.alias}</div>
                      <div className="muted" style={{ fontSize: 12 }}>
                        {b.name}
                      </div>
                    </td>
                    <td className="num mono nowrap">{fmtCr(b.amount_cr)}</td>
                    <td style={{ textAlign: "right" }}>
                      <div className="stack stack--sm" style={{ alignItems: "flex-end" }}>
                        {statusOf[b.vendor_id] && <StatusBadge status={statusOf[b.vendor_id]} />}
                        {inv.length > 0 && (
                          <span style={{ fontSize: 11.5, color: levelColor(inv[0].level) }}>
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
