import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BadgeCheck,
  Brain,
  ClipboardCheck,
  FlaskConical,
  Gavel,
  History,
  RotateCcw,
  Save,
  SearchCheck,
  ShieldQuestion,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { Decision, EvidenceItem, EvidenceSource, Finding } from "../api/types";
import { ErrorCard } from "../components/NotLoaded";
import {
  Badge,
  Button,
  Callout,
  Card,
  DocLink,
  EmptyState,
  FamilyDot,
  LevelBadge,
  LoadingBlock,
  Meter,
  StatusBadge,
  Switch,
  useToast,
} from "../components/ui";
import { CATEGORY_LABEL, FAMILY_LABEL, fmtDateTime, humanize, levelColor, vendorLetter } from "../lib/format";
import { isNotLoaded, useFinding } from "../lib/hooks";

const THRESHOLDS = [0.45, 0.9];

function SourceChip({ src }: { src: EvidenceSource }) {
  if ((src.kind === "document" || src.kind === "tender_clause") && src.document_id)
    return (
      <a className="source-chip" href={api.documentUrl(src.document_id, src.page)} target="_blank" rel="noreferrer">
        {src.filename ?? src.document_id}
        {src.page ? ` · p.${src.page}` : ""}
        {src.clause ? ` · cl.${src.clause}` : ""}
      </a>
    );
  if (src.kind === "vendor_registry")
    return (
      <span className="source-chip">
        registry · {src.vendor_id} · {String(src.field)}
        {src.value ? `: ${String(src.value).slice(0, 48)}` : ": missing"}
      </span>
    );
  if (src.kind === "award_record") return <span className="source-chip mono">{src.tender_id}</span>;
  if (src.kind === "model") return <span className="source-chip">{String(src.model)} model</span>;
  return null;
}

function EvidenceRow({ item, included, onToggle, testable }: { item: EvidenceItem; included: boolean; onToggle: (v: boolean) => void; testable: boolean }) {
  const [more, setMore] = useState(false);
  const awards = item.sources.filter((s) => s.kind === "award_record");
  const passages = item.sources.filter((s) => s.kind === "passage");
  const other = item.sources.filter((s) => s.kind !== "award_record" && s.kind !== "passage");
  return (
    <div className={`evidence${included ? "" : " removed"}`}>
      <span className="evidence__id">{item.evidence_id}</span>
      <div style={{ minWidth: 0 }}>
        <div className="row" style={{ gap: 8 }}>
          <span className="evidence__label">{item.label}</span>
          <span className="chip" style={{ padding: "1px 8px" }}>
            <FamilyDot family={item.family} />
            {FAMILY_LABEL[item.family] ?? item.family}
          </span>
          {testable && <span className="muted mono" style={{ fontSize: 11 }}>w {item.weight.toFixed(2)}</span>}
        </div>
        <p className="evidence__statement">{item.statement}</p>
        <div className="evidence__sources">
          {other.map((s, i) => (
            <SourceChip key={i} src={s} />
          ))}
          {awards.length > 0 && (
            <button className="source-chip" style={{ cursor: "pointer" }} onClick={() => setMore((m) => !m)}>
              {awards.length} award records {more ? "▴" : "▾"}
            </button>
          )}
          {passages.length > 0 && (
            <button className="source-chip" style={{ cursor: "pointer" }} onClick={() => setMore((m) => !m)}>
              {passages.length} matching passages {more ? "▴" : "▾"}
            </button>
          )}
        </div>
        {more && awards.length > 0 && (
          <table className="table" style={{ marginTop: 8, fontSize: 12 }}>
            <tbody>
              {awards.map((a) => (
                <tr key={String(a.tender_id)}>
                  <td className="mono">{a.tender_id}</td>
                  {Object.entries(a.outcomes ?? {}).map(([v, o]) => (
                    <td key={v}>
                      <span className="muted">{v}</span>{" "}
                      <Badge tone={o === "WON" ? "brand" : o === "RUNNER_UP" ? "accent" : "outline"}>{o.replace("_", "-")}</Badge>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {more &&
          passages.map((p, i) => (
            <div key={i} className="passage" style={{ marginTop: 8 }}>
              <div>
                <div className="passage__meta">
                  <span>{String(p.section)} · p.{p.a?.page}</span>
                  <span className="mono">{Math.round(Number(p.similarity) * 100)}%</span>
                </div>
                {p.a?.text}
              </div>
              <div>
                <div className="passage__meta">
                  <span>p.{p.b?.page}</span>
                </div>
                {p.b?.text}
              </div>
            </div>
          ))}
      </div>
      {testable ? <Switch checked={included} onChange={onToggle} label={`Include ${item.label}`} /> : <span />}
    </div>
  );
}

function Disposition({ finding }: { finding: Finding }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [decision, setDecision] = useState<Decision>(finding.status === "OPEN" ? "FURTHER_REVIEW" : (finding.status as Decision));
  const [auditor, setAuditor] = useState(() => {
    try {
      return localStorage.getItem("ts-auditor") ?? "";
    } catch {
      return "";
    }
  });
  const [notes, setNotes] = useState("");
  const save = useMutation({
    mutationFn: () => api.disposition(finding.finding_id, decision, auditor, notes),
    onSuccess: () => {
      try {
        localStorage.setItem("ts-auditor", auditor);
      } catch {
        /* storage unavailable */
      }
      setNotes("");
      toast(
        <span>
          Disposition <b>{humanize(decision)}</b> recorded in the audit chain
        </span>,
      );
      return qc.invalidateQueries();
    },
  });
  const OPTS: { key: Decision; label: string; hint: string }[] = [
    { key: "VERIFIED", label: "Verified", hint: "Signal confirmed" },
    { key: "FURTHER_REVIEW", label: "Further review", hint: "Needs investigation" },
    { key: "DISMISSED", label: "Dismissed", hint: "Legitimate explanation" },
  ];
  return (
    <Card title="Auditor disposition" icon={<Gavel size={15} />} actions={<StatusBadge status={finding.status} />}>
      <div className="stack">
        <p className="muted" style={{ fontSize: 12.5 }}>
          The system finds, explains and supports. The final decision is yours and becomes part of the tamper-evident audit history.
        </p>
        <div className="decision">
          {OPTS.map((o) => (
            <button key={o.key} className={`decision__opt${decision === o.key ? " selected" : ""}`} onClick={() => setDecision(o.key)}>
              {o.label}
              <small>{o.hint}</small>
            </button>
          ))}
        </div>
        <div className="field">
          <label htmlFor="auditor">Auditor</label>
          <input id="auditor" className="input" value={auditor} onChange={(e) => setAuditor(e.target.value)} placeholder="Your name" />
        </div>
        <div className="field">
          <label htmlFor="notes">Notes</label>
          <textarea id="notes" className="textarea" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Verify directorship with MCA records" />
        </div>
        {save.isError && <Callout tone="danger">{String(save.error)}</Callout>}
        <Button variant="primary" icon={<ClipboardCheck size={15} />} loading={save.isPending} disabled={!auditor.trim()} onClick={() => save.mutate()}>
          Record disposition
        </Button>
      </div>
    </Card>
  );
}

function RobustnessPanel({ fid }: { fid: string }) {
  const q = useQuery({ queryKey: ["robustness", fid], queryFn: () => api.robustness(fid) });
  if (q.isLoading) return <LoadingBlock rows={3} />;
  if (!q.data) return null;
  const r = q.data;
  return (
    <div className="stack">
      <div className="row row--between">
        <div>
          <div className="section-label">Robustness score</div>
          <div style={{ fontSize: 28, fontWeight: 600, letterSpacing: "-0.02em" }}>{Math.round(r.robustness_score * 100)}%</div>
        </div>
        <p className="dim" style={{ maxWidth: "36ch", fontSize: 13, textAlign: "right" }}>
          {r.interpretation}
        </p>
      </div>
      <div className="stack stack--sm">
        <div className="section-label">Remove one item at a time</div>
        {r.leave_one_out.map((l) => (
          <div key={l.evidence_id} className="bar-row" style={{ gridTemplateColumns: "210px 1fr 90px" }}>
            <span style={{ fontSize: 12.5 }}>
              <span className="mono muted">{l.evidence_id}</span> {l.label}
            </span>
            <div className="bar">
              <div className="bar__fill" style={{ width: `${Math.min(100, (l.support_after / 1.5) * 100)}%`, background: levelColor(l.level_after) }} />
            </div>
            <span style={{ textAlign: "right" }}>
              <LevelBadge level={l.level_after} />
            </span>
          </div>
        ))}
      </div>
      <div className="stack stack--sm">
        <div className="section-label">Remove a whole evidence family</div>
        {r.family_ablation.map((f) => (
          <div key={f.family} className="row row--between" style={{ fontSize: 13 }}>
            <span className="row" style={{ gap: 8 }}>
              <FamilyDot family={f.family} />
              without {FAMILY_LABEL[f.family]?.toLowerCase()} evidence
            </span>
            <span className="row" style={{ gap: 6 }}>
              <Badge tone={f.status === "STILL_SUPPORTED" ? "pass" : "medium"}>{humanize(f.status)}</Badge>
              <LevelBadge level={f.level_after} />
            </span>
          </div>
        ))}
      </div>
      {r.minimal_breaking_set && (
        <Callout>
          Smallest removal that drops the finding below escalation: <b>{r.minimal_breaking_set.labels.join(" + ")}</b> ({r.minimal_breaking_set.size} items).
        </Callout>
      )}
    </div>
  );
}

export function FindingDetail() {
  const { findingId = "" } = useParams();
  const q = useFinding(findingId);
  const qc = useQueryClient();
  const toast = useToast();
  const [removed, setRemoved] = useState<string[]>([]);
  const removedKey = useMemo(() => [...removed].sort(), [removed]);
  const testable = q.data?.category === "INVESTIGATION_SIGNAL";

  const cf = useQuery({
    queryKey: ["cf-preview", findingId, removedKey],
    queryFn: () => api.counterfactual(findingId, removedKey, false),
    enabled: testable && removedKey.length > 0,
    placeholderData: (prev) => prev,
  });
  const record = useMutation({
    mutationFn: () => api.counterfactual(findingId, removedKey, true),
    onSuccess: (r) => {
      toast(
        <span>
          Robustness test #{r.run_id} recorded: <b>{humanize(r.status)}</b>
        </span>,
      );
      return qc.invalidateQueries({ queryKey: ["finding", findingId] });
    },
  });

  if (q.isLoading) return <LoadingBlock rows={8} />;
  if (q.error)
    return isNotLoaded(q.error) ? (
      <Card>
        <EmptyState icon={<ShieldQuestion size={30} />} title="Finding not found" action={<Link to="/findings">Back to findings</Link>}>
          The analysis may have been re-run. Open the findings list to pick a current finding.
        </EmptyState>
      </Card>
    ) : (
      <ErrorCard error={q.error} />
    );
  const f = q.data!;
  const active = removedKey.length > 0 && cf.data;
  const level = active ? cf.data!.counterfactual.level : f.level;
  const support = active ? cf.data!.counterfactual.support : Number(f.assessment.support ?? 0);
  const originalSupport = Number(f.assessment.support ?? 0);
  const maxSupport = Math.max(1.5, originalSupport);
  const removedSet = new Set(removedKey);
  const toggle = (id: string, include: boolean) => setRemoved((r) => (include ? r.filter((x) => x !== id) : [...r, id]));
  const presets = testable
    ? [
        { label: "Remove shared director", ids: f.evidence.filter((e) => e.type === "SHARED_DIRECTOR").map((e) => e.evidence_id) },
        { label: "Remove behavioural signals", ids: f.evidence.filter((e) => ["behavioural", "model"].includes(e.family)).map((e) => e.evidence_id) },
        { label: "Remove document similarity", ids: f.evidence.filter((e) => e.family === "document").map((e) => e.evidence_id) },
      ].filter((p) => p.ids.length)
    : [];

  return (
    <>
      <Link to="/findings" className="row muted" style={{ gap: 6, fontSize: 13 }}>
        <ArrowLeft size={14} /> All findings
      </Link>

      <section className="case-head">
        <span className="case-head__rail" style={{ background: levelColor(level) }} />
        <div className="row row--between" style={{ alignItems: "flex-start", position: "relative" }}>
          <div className="stack" style={{ gap: 12 }}>
            <div className="row">
              <span className="mono" style={{ color: "var(--brand)", fontSize: 12, fontWeight: 600 }}>
                {f.finding_id}
              </span>
              <span className="muted" style={{ fontSize: 12 }}>
                {CATEGORY_LABEL[f.category]}
              </span>
            </div>
            <h1>{f.signal}</h1>
            <div className="row">
              {f.subject.vendors.map((v) => (
                <span key={v.vendor_id} className="vendor-pill">
                  <span className="vendor-pill__av">{vendorLetter(v)}</span>
                  <span>
                    <b>{v.alias ?? v.name}</b> <span className="muted">{v.name}</span>
                  </span>
                </span>
              ))}
            </div>
          </div>
          <div className="level-dial">
            <span className="muted" style={{ fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase" }}>
              {active ? "Counterfactual level" : "Assessed level"}
            </span>
            <span className="level-dial__value" style={{ color: levelColor(level) }}>
              {level === "INSUFFICIENT_DATA" ? "NO DATA" : level}
            </span>
            {active && (
              <span className="muted" style={{ fontSize: 12 }}>
                was <b>{f.level}</b>
              </span>
            )}
          </div>
        </div>
        {testable && (
          <div style={{ marginTop: 20, position: "relative" }}>
            <div className="row row--between" style={{ fontSize: 12, marginBottom: 6 }}>
              <span>
                Evidence support <b className="mono">{support.toFixed(2)}</b>
                {active && <span className="mono"> (from {originalSupport.toFixed(2)})</span>}
              </span>
              <span className="mono muted">MEDIUM ≥ 0.45 · HIGH ≥ 0.90 + behavioural + 2 families</span>
            </div>
            <Meter value={support} max={maxSupport} color={levelColor(level)} ticks={THRESHOLDS} />
          </div>
        )}
      </section>

      <div className="grid grid--main-side">
        <Card
          title={testable ? "Supporting evidence · robustness test" : "Supporting evidence"}
          icon={testable ? <FlaskConical size={15} /> : <SearchCheck size={15} />}
          flush
          actions={
            testable && (
              <>
                {removedKey.length > 0 && (
                  <Button size="sm" icon={<RotateCcw size={13} />} onClick={() => setRemoved([])}>
                    Reset
                  </Button>
                )}
                <Button size="sm" variant="primary" icon={<Save size={13} />} disabled={!removedKey.length} loading={record.isPending} onClick={() => record.mutate()}>
                  Record test
                </Button>
              </>
            )
          }
        >
          {testable && (
            <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)", background: "var(--surface-2)" }} className="stack stack--sm">
              <span className="dim" style={{ fontSize: 13 }}>
                <b>Does this finding still hold if evidence is removed?</b> Switch items off to re-score the finding live with the same explicit rule.
              </span>
              <div className="row">
                {presets.map((p) => (
                  <Button key={p.label} size="sm" onClick={() => setRemoved(p.ids)}>
                    {p.label}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {active && (
            <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)" }}>
              <Callout tone={cf.data!.status === "STILL_SUPPORTED" ? "ok" : cf.data!.status === "DOWNGRADED" ? "warn" : "danger"}>
                <b>{humanize(cf.data!.status)}.</b> {cf.data!.explanation}
              </Callout>
            </div>
          )}
          {f.evidence.map((e) => (
            <EvidenceRow key={e.evidence_id} item={e} included={!removedSet.has(e.evidence_id)} onToggle={(v) => toggle(e.evidence_id, v)} testable={testable} />
          ))}
        </Card>

        <div className="stack sticky-side" style={{ gap: 18 }}>
          <Disposition finding={f} />

          {f.evidence.some((e) => e.sources.some((s) => s.kind === "document" && s.document_id)) && (
            <Card title="Source documents">
              <div className="stack stack--sm">
                {[...new Map(f.evidence.flatMap((e) => e.sources).filter((s) => s.kind === "document" && s.document_id).map((s) => [s.document_id, s])).values()].map((s) => (
                  <DocLink key={s.document_id} documentId={s.document_id!} page={s.page} label={s.filename ?? s.document_id} />
                ))}
              </div>
            </Card>
          )}

          <Card title="Audit trail" icon={<History size={15} />}>
            {f.audit.length === 0 && <p className="muted">No auditor actions yet.</p>}
            <div className="timeline">
              {[...f.audit].reverse().map((e) => (
                <div key={e.entry_id} className="timeline__item">
                  <span className="timeline__dot" />
                  <div>
                    <div className="row" style={{ gap: 8 }}>
                      <b style={{ fontSize: 13 }}>{humanize(e.action)}</b>
                      {e.payload.decision ? <StatusBadge status={String(e.payload.decision)} /> : null}
                      {e.payload.status ? <Badge tone="outline">{humanize(String(e.payload.status))}</Badge> : null}
                    </div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {e.actor} · {fmtDateTime(e.created_at)}
                    </div>
                    {e.payload.notes ? <p style={{ fontSize: 12.5, marginTop: 4 }}>{String(e.payload.notes)}</p> : null}
                    <div className="mono muted" style={{ fontSize: 10.5, marginTop: 2 }}>
                      #{e.entry_hash.slice(0, 16)}…
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <div className={testable ? "grid grid--2" : "stack"} style={{ alignItems: "start" }}>
        <Card title="Why was this flagged?" icon={<Brain size={15} />}>
          <div className="reason">
            {f.reasoning.steps.map((s) => {
              const ids = s.evidence_ids ?? [];
              const inactive = ids.length > 0 && ids.every((id) => removedSet.has(id));
              return (
                <div key={s.step} className={`reason__step${inactive ? " inactive" : ""}`}>
                  <span className="reason__num">{s.step}</span>
                  <div>
                    <div className="reason__title row" style={{ gap: 8 }}>
                      {s.label}
                      {ids.map((id) => (
                        <span key={id} className="badge badge--outline mono" style={{ height: 18, fontSize: 10.5 }}>
                          {id}
                        </span>
                      ))}
                    </div>
                    <p className="reason__body">{s.statement}</p>
                  </div>
                </div>
              );
            })}
            <div className="reason__conclusion">
              <span className="reason__num" style={{ background: levelColor(level) }}>
                <BadgeCheck size={15} />
              </span>
              <div>
                <div className="reason__title">{active ? `Counterfactual: ${level}` : `Conclusion: ${f.level}`}</div>
                <p className="reason__body">{active ? cf.data!.explanation : f.reasoning.conclusion}</p>
              </div>
            </div>
          </div>
        </Card>

        {testable && (
          <Card title="Finding robustness report" icon={<FlaskConical size={15} />}>
            <RobustnessPanel fid={f.finding_id} />
          </Card>
        )}
      </div>
    </>
  );
}
