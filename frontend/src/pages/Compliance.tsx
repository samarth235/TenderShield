import { Check, CircleHelp, Minus, X } from "lucide-react";
import { useMemo, useState } from "react";

import { ErrorCard, NotLoaded } from "../components/NotLoaded";
import { Badge, Callout, Card, DocLink, Drawer, LoadingBlock, PageHead, ResultBadge, StatusBadge, Switch } from "../components/ui";
import { isNotLoaded, useCompliance } from "../lib/hooks";
import type { Evaluation } from "../api/types";

const ICON = {
  PASS: <Check size={13} strokeWidth={3} />,
  FAIL: <X size={13} strokeWidth={3} />,
  UNKNOWN: <CircleHelp size={13} strokeWidth={2.5} />,
  NOT_APPLICABLE: <Minus size={13} strokeWidth={3} />,
};

export function Compliance() {
  const q = useCompliance();
  const [open, setOpen] = useState<{ vendor: string; rule: string } | null>(null);
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

  const totals = m.vendors.reduce(
    (a, v) => ({ PASS: a.PASS + v.counts.PASS, FAIL: a.FAIL + v.counts.FAIL, UNKNOWN: a.UNKNOWN + v.counts.UNKNOWN, NA: a.NA + v.counts.NOT_APPLICABLE }),
    { PASS: 0, FAIL: 0, UNKNOWN: 0, NA: 0 },
  );
  const hasIssue = (ruleId: string) =>
    m.vendors.some((v) => ["FAIL", "UNKNOWN"].includes(m.cells[v.vendor_id]?.[ruleId]?.result ?? ""));

  const cell: Evaluation | undefined = open ? m.cells[open.vendor]?.[open.rule] : undefined;
  const rule = open ? m.rules.find((r) => r.rule_id === open.rule) : undefined;
  const vendor = open ? m.vendors.find((v) => v.vendor_id === open.vendor) : undefined;

  return (
    <>
      <PageHead
        step="02"
        eyebrow="Deterministic compliance engine"
        title={`${m.evaluations} compliance evaluations`}
        sub={`${m.vendors.length} bidders × ${m.rules.length} rules. Each result records the expected condition, the actual value, the source document and page, and the reason. Missing evidence is UNKNOWN, never FAIL.`}
        actions={
          <>
            <Badge tone="pass">{totals.PASS} pass</Badge>
            <Badge tone="fail">{totals.FAIL} fail</Badge>
            <Badge tone="unknown">{totals.UNKNOWN} unknown</Badge>
            <Badge tone="na">{totals.NA} n/a</Badge>
          </>
        }
      />

      <Card
        flush
        title="Compliance matrix"
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
                        <span className="matrix__rule-id">{r.rule_id}</span>
                        {r.requirement}
                        {!r.mandatory && (
                          <Badge tone="outline">
                            optional
                          </Badge>
                        )}
                      </td>
                      {m.vendors.map((v) => {
                        const c = m.cells[v.vendor_id]?.[r.rule_id];
                        if (!c) return <td key={v.vendor_id} className="matrix__cell" />;
                        return (
                          <td key={v.vendor_id} className="matrix__cell">
                            <button
                              className={`cell-btn cell--${c.result}${c.mandatory ? "" : " cell--optional"}`}
                              onClick={() => setOpen({ vendor: v.vendor_id, rule: r.rule_id })}
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

      <div className="legend">
        <span className="legend__item"><span className="legend__swatch cell--PASS" /> Pass</span>
        <span className="legend__item"><span className="legend__swatch cell--FAIL" /> Fail (mandatory)</span>
        <span className="legend__item"><span className="legend__swatch cell--FAIL cell--optional" /> Fail (optional)</span>
        <span className="legend__item"><span className="legend__swatch cell--UNKNOWN" /> Unknown / insufficient data</span>
        <span className="legend__item"><span className="legend__swatch cell--NOT_APPLICABLE" /> Not applicable</span>
      </div>

      {open && cell && rule && vendor && (
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
          <div className="stack stack--sm">
            <div className="section-label">Source clause</div>
            <DocLink documentId={rule.source.document_id} page={rule.source.page} label={`${rule.source.filename} · clause ${rule.source.clause}`} />
          </div>
        </Drawer>
      )}
    </>
  );
}
