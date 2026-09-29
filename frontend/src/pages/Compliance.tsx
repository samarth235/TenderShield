import { Bot, Check, ChevronRight, CircleHelp, Code2, FileText, Minus, Quote, X } from "lucide-react";
import { useMemo, useState } from "react";

import { ErrorCard, NotLoaded } from "../components/NotLoaded";
import { Badge, Callout, Card, DocLink, Drawer, LoadingBlock, PageHead, ResultBadge, StatusBadge, Switch } from "../components/ui";
import { isNotLoaded, useCompliance, useRules } from "../lib/hooks";
import type { ComplianceMatrix, Evaluation, Rule } from "../api/types";

const ICON = {
  PASS: <Check size={13} strokeWidth={3} />,
  FAIL: <X size={13} strokeWidth={3} />,
  UNKNOWN: <CircleHelp size={13} strokeWidth={2.5} />,
  NOT_APPLICABLE: <Minus size={13} strokeWidth={3} />,
};

const OP: Record<string, string> = {
  gte: "≥",
  gt: ">",
  lte: "≤",
  eq: "=",
  is_true: "is",
  is_false: "is",
  valid_on_submission: "valid on",
  submitted_before: "≤",
};

function MachineRule({ rule }: { rule: Rule }) {
  const rhs =
    rule.operator === "is_true"
      ? "true"
      : rule.operator === "is_false"
        ? "false"
        : rule.operator === "valid_on_submission"
          ? "bid_submission_date"
          : String(rule.threshold);
  return (
    <div className="code">
      <span>{rule.metric}</span> <span className="tok-op">{OP[rule.operator] ?? rule.operator}</span> <span>{rhs}</span>
      {rule.unit && !["is_true", "is_false"].includes(rule.operator) ? <span style={{ opacity: 0.6 }}> {rule.unit}</span> : null}
      {rule.applies_if && (
        <div style={{ opacity: 0.75, marginTop: 6 }}>
          <span className="tok-op">when</span> {rule.applies_if.metric} = {String(rule.applies_if.threshold)}
        </div>
      )}
    </div>
  );
}

/** How the AI read the tender clause and turned it into a deterministic check. */
function RuleDerivation({ rule }: { rule: Rule }) {
  return (
    <div className="chain">
      <div className="chain__node">
        <span className="chain__icon chain__icon--brand">
          <Quote size={13} />
        </span>
        <div className="chain__label">Tender clause</div>
        <div className="quote">{rule.clause_text}</div>
        <div className="row" style={{ marginTop: 8 }}>
          <DocLink documentId={rule.source.document_id} page={rule.source.page} label={rule.source.filename} />
          <span className="muted" style={{ fontSize: 12 }}>
            Clause {rule.source.clause}
          </span>
        </div>
      </div>
      <div className="chain__node">
        <span className="chain__icon">
          <Bot size={13} />
        </span>
        <div className="chain__label">AI extraction</div>
        <div className="row">
          <Badge tone="accent">{rule.extraction.method === "llm" ? rule.extraction.model ?? "LLM" : "pattern library"}</Badge>
          <span style={{ fontSize: 13 }}>
            Confidence {(rule.extraction.confidence * 100).toFixed(0)}% · metric <span className="mono">{rule.metric}</span>
          </span>
        </div>
        {rule.notes.map((n) => (
          <p key={n} className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>
            {n}
          </p>
        ))}
      </div>
      <div className="chain__node">
        <span className="chain__icon">
          <Code2 size={13} />
        </span>
        <div className="chain__label">Deterministic check</div>
        <MachineRule rule={rule} />
      </div>
    </div>
  );
}

function RuleDrawer({ rule, m, onClose, onOpenCell }: { rule: Rule; m: ComplianceMatrix; onClose: () => void; onOpenCell: (vendor: string) => void }) {
  return (
    <Drawer
      onClose={onClose}
      title={
        <span className="row">
          <span className="mono muted">{rule.rule_id}</span> {rule.requirement}
        </span>
      }
      sub={
        <>
          {rule.category} · {rule.mandatory ? "Mandatory" : "Desirable"}
        </>
      }
    >
      <RuleDerivation rule={rule} />
      <div className="stack stack--sm">
        <div className="section-label">
          <FileText size={11} style={{ verticalAlign: -1, marginRight: 4 }} />
          Result for every bidder
        </div>
        <div className="grid grid--2" style={{ gap: 8 }}>
          {m.vendors.map((v) => {
            const cell = m.cells[v.vendor_id]?.[rule.rule_id];
            return (
              <button key={v.vendor_id} className="card card--inset vendor-result" onClick={() => onOpenCell(v.vendor_id)}>
                <div className="row row--between">
                  <b style={{ fontSize: 13 }}>{v.alias ?? v.name}</b>
                  {cell && <ResultBadge result={cell.result} />}
                </div>
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {cell?.actual != null ? String(cell.actual) : "no value"}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </Drawer>
  );
}

type Open = { kind: "rule"; rule: string } | { kind: "cell"; vendor: string; rule: string };

export function Compliance() {
  const q = useCompliance();
  const rules = useRules();
  const [open, setOpen] = useState<Open | null>(null);
  const [issuesOnly, setIssuesOnly] = useState(false);

  const groups = useMemo(() => {
    const out: Record<string, NonNullable<typeof q.data>["rules"]> = {};
    q.data?.rules.forEach((r) => (out[r.category] ??= []).push(r));
    return out;
  }, [q.data]);

  if (q.isLoading) return <LoadingBlock rows={8} />;
  if (q.error) return isNotLoaded(q.error) ? <NotLoaded what="compliance results" /> : <ErrorCard error={q.error} />;
  const m = q.data!;
  if (!m.evaluations) return <NotLoaded what="compliance results" />;
  const book = rules.data;
  const fullRule = (id: string) => book?.rules.find((r) => r.rule_id === id);

  const totals = m.vendors.reduce(
    (a, v) => ({ PASS: a.PASS + v.counts.PASS, FAIL: a.FAIL + v.counts.FAIL, UNKNOWN: a.UNKNOWN + v.counts.UNKNOWN, NA: a.NA + v.counts.NOT_APPLICABLE }),
    { PASS: 0, FAIL: 0, UNKNOWN: 0, NA: 0 },
  );
  const hasIssue = (ruleId: string) =>
    m.vendors.some((v) => ["FAIL", "UNKNOWN"].includes(m.cells[v.vendor_id]?.[ruleId]?.result ?? ""));

  const cell: Evaluation | undefined = open?.kind === "cell" ? m.cells[open.vendor]?.[open.rule] : undefined;
  const rule = open ? m.rules.find((r) => r.rule_id === open.rule) : undefined;
  const derived = open ? fullRule(open.rule) : undefined;
  const vendor = open?.kind === "cell" ? m.vendors.find((v) => v.vendor_id === open.vendor) : undefined;

  return (
    <>
      <PageHead
        eyebrow="AI rule extraction · deterministic compliance"
        title="Rules & compliance"
        sub={`The AI reads each tender clause and proposes a machine-checkable rule; the rule engine then evaluates ${m.vendors.length} bidders × ${m.rules.length} rules. Missing evidence is UNKNOWN, never FAIL. The AI never declares a bidder compliant.`}
        actions={
          <>
            {book && <Badge tone="accent">{book.method === "llm" ? `Claude · ${book.model}` : "Pattern extractor"}</Badge>}
            <Badge tone="pass">{totals.PASS} pass</Badge>
            <Badge tone="fail">{totals.FAIL} fail</Badge>
            <Badge tone="unknown">{totals.UNKNOWN} unknown</Badge>
            <Badge tone="na">{totals.NA} n/a</Badge>
          </>
        }
      />
      {book?.warnings.map((w) => (
        <Callout key={w} tone="warn">
          {w}
        </Callout>
      ))}

      <Card
        flush
        title={`Compliance matrix · ${m.evaluations} evaluations`}
        actions={
          <label className="row" style={{ gap: 8, fontSize: 13, cursor: "pointer" }}>
            <Switch checked={issuesOnly} onChange={setIssuesOnly} label="Show only rules with issues" />
            Only rules with issues
          </label>
        }
      >
        <div style={{ overflowX: "auto" }}>
          <table className="matrix">
            <thead>
              <tr>
                <th>
                  <span className="section-label">Requirement</span>
                </th>
                {m.vendors.map((v) => (
                  <th key={v.vendor_id}>
                    <div className="matrix__vendor">
                      {v.alias ?? v.name}
                      <StatusBadge status={v.status} />
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(groups).map(([category, rules]) => {
                const visible = rules.filter((r) => !issuesOnly || hasIssue(r.rule_id));
                if (!visible.length) return null;
                return [
                  <tr key={`g-${category}`} className="matrix__group">
                    <td colSpan={m.vendors.length + 1}>{category}</td>
                  </tr>,
                  ...visible.map((r) => (
                    <tr key={r.rule_id}>
                      <td className="matrix__rule">
                        {fullRule(r.rule_id) ? (
                          <button className="matrix__rule-btn" onClick={() => setOpen({ kind: "rule", rule: r.rule_id })} title="Show clause and AI extraction">
                            <span className="matrix__rule-id">{r.rule_id}</span>
                            {r.requirement}
                          </button>
                        ) : (
                          <>
                            <span className="matrix__rule-id">{r.rule_id}</span>
                            {r.requirement}
                          </>
                        )}
                        {!r.mandatory && <Badge tone="outline">optional</Badge>}
                      </td>
                      {m.vendors.map((v) => {
                        const c = m.cells[v.vendor_id]?.[r.rule_id];
                        if (!c) return <td key={v.vendor_id} className="matrix__cell" />;
                        return (
                          <td key={v.vendor_id} className="matrix__cell">
                            <button
                              className={`cell-btn cell--${c.result}${c.mandatory ? "" : " cell--optional"}`}
                              onClick={() => setOpen({ kind: "cell", vendor: v.vendor_id, rule: r.rule_id })}
                              title={c.reason}
                            >
                              {ICON[c.result]}
                              {c.result === "NOT_APPLICABLE" ? "N/A" : c.result === "UNKNOWN" ? "?" : ""}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  )),
                ];
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="row row--between">
        <div className="legend">
          <span className="legend__item"><span className="legend__swatch cell--PASS" /> Pass</span>
          <span className="legend__item"><span className="legend__swatch cell--FAIL" /> Fail (mandatory)</span>
          <span className="legend__item"><span className="legend__swatch cell--FAIL cell--optional" /> Fail (optional)</span>
          <span className="legend__item"><span className="legend__swatch cell--UNKNOWN" /> Unknown / insufficient data</span>
          <span className="legend__item"><span className="legend__swatch cell--NOT_APPLICABLE" /> Not applicable</span>
        </div>
        <span className="muted" style={{ fontSize: 12 }}>
          Click a requirement to see its clause and AI extraction · click a result for its evidence
        </span>
      </div>

      {open?.kind === "rule" && derived && (
        <RuleDrawer rule={derived} m={m} onClose={() => setOpen(null)} onOpenCell={(v) => setOpen({ kind: "cell", vendor: v, rule: derived.rule_id })} />
      )}

      {open?.kind === "cell" && cell && rule && vendor && (
        <Drawer
          onClose={() => setOpen(null)}
          title={
            <span className="row">
              {vendor.alias ?? vendor.name} <ResultBadge result={cell.result} />
            </span>
          }
          sub={
            <>
              <span className="mono">{rule.rule_id}</span> · {rule.requirement}
            </>
          }
        >
          {cell.result === "UNKNOWN" && (
            <Callout tone="warn">Missing data is not treated as wrongdoing. This result lowers what the system can verify; it is not an adverse finding.</Callout>
          )}
          <dl className="kv">
            <dt>Expected</dt>
            <dd className="mono">{cell.expected}</dd>
            <dt>Actual</dt>
            <dd className="mono">{cell.actual == null ? "—" : String(cell.actual)}</dd>
            <dt>Mandatory</dt>
            <dd>{cell.mandatory ? "Yes" : "No (desirable)"}</dd>
          </dl>
          <div>
            <div className="section-label" style={{ marginBottom: 6 }}>Reason</div>
            <p>{cell.reason}</p>
          </div>
          <div className="stack stack--sm">
            <div className="section-label">Evidence</div>
            {cell.evidence.length === 0 && <p className="muted">No supporting document was found.</p>}
            {cell.evidence.map((e, i) => (
              <div key={i} className="card card--inset" style={{ padding: 12 }}>
                <div className="row row--between" style={{ marginBottom: 6 }}>
                  <Badge tone="outline">{e.role === "reference_date" ? "Reference date" : e.role === "applicability" ? "Applicability" : "Primary evidence"}</Badge>
                  {e.document_id && <DocLink documentId={e.document_id} page={e.page} label={e.filename ?? e.document_id} />}
                </div>
                {e.excerpt && <div className="quote mono" style={{ fontSize: 12 }}>{e.excerpt}</div>}
              </div>
            ))}
          </div>
          {derived ? (
            <details className="disclosure">
              <summary>
                <ChevronRight size={14} className="disclosure__chev" />
                How this rule was derived
                <span className="muted" style={{ fontWeight: 400, marginLeft: "auto", fontSize: 12 }}>
                  clause {derived.source.clause}
                </span>
              </summary>
              <div className="disclosure__body">
                <RuleDerivation rule={derived} />
              </div>
            </details>
          ) : (
            <div className="stack stack--sm">
              <div className="section-label">Source clause</div>
              <DocLink documentId={rule.source.document_id} page={rule.source.page} label={`${rule.source.filename} · clause ${rule.source.clause}`} />
            </div>
          )}
        </Drawer>
      )}
    </>
  );
}
