import { Bot, Code2, FileText, ListChecks, Quote } from "lucide-react";
import { useState } from "react";

import { ErrorCard, NotLoaded } from "../components/NotLoaded";
import { Badge, Callout, Card, DocLink, LoadingBlock, PageHead, ResultBadge } from "../components/ui";
import { isNotLoaded, useCompliance, useRules } from "../lib/hooks";
import type { Rule } from "../api/types";

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

export function Rulebook() {
  const rules = useRules();
  const compliance = useCompliance();
  const [selected, setSelected] = useState<string | null>(null);

  if (rules.isLoading) return <LoadingBlock rows={8} />;
  if (rules.error) return isNotLoaded(rules.error) ? <NotLoaded what="rulebook" /> : <ErrorCard error={rules.error} />;
  const book = rules.data!;
  if (!book.rules.length) return <NotLoaded what="rulebook" />;
  const rule = book.rules.find((r) => r.rule_id === selected) ?? book.rules[0];
  const results = compliance.data?.vendors.map((v) => ({ v, cell: compliance.data!.cells[v.vendor_id]?.[rule.rule_id] })) ?? [];

  return (
    <>
      <PageHead
        step="01"
        eyebrow="AI tender understanding"
        title="Tender Rulebook"
        sub="The AI reads each natural-language clause and proposes a candidate rule. The rule is converted into a deterministic, machine-checkable condition that keeps its source clause and page. The AI never declares a bidder compliant."
        actions={
          <>
            <Badge tone="accent">{book.method === "llm" ? `Claude · ${book.model}` : "Pattern extractor"}</Badge>
            <Badge tone="outline">
              {book.rules.length} rules · {book.rules.filter((r) => r.mandatory).length} mandatory
            </Badge>
          </>
        }
      />
      {book.warnings.map((w) => (
        <Callout key={w} tone="warn">
          {w}
        </Callout>
      ))}

      <div className="grid grid--side-main">
        <Card title="Requirements" icon={<ListChecks size={15} />} flush>
          <div className="rule-list">
            {book.rules.map((r) => (
              <button
                key={r.rule_id}
                className={`rule-item${r.rule_id === rule.rule_id ? " active" : ""}`}
                onClick={() => setSelected(r.rule_id)}
              >
                <span className="rule-item__id">{r.rule_id}</span>
                <span className="rule-item__text">
                  {r.requirement}
                  <span className="muted" style={{ display: "block", fontSize: 11.5, marginTop: 2 }}>
                    {r.category} · clause {r.source.clause}
                  </span>
                </span>
                {!r.mandatory && <Badge tone="outline">optional</Badge>}
              </button>
            ))}
          </div>
        </Card>

        <div className="stack">
          <Card
            title={
              <>
                <span className="mono muted">{rule.rule_id}</span> {rule.requirement}
              </>
            }
            actions={<Badge tone={rule.mandatory ? "brand" : "outline"}>{rule.mandatory ? "Mandatory" : "Desirable"}</Badge>}
          >
            <div className="chain">
              <div className="chain__node">
                <span className="chain__icon chain__icon--brand">
                  <Quote size={13} />
                </span>
                <div className="chain__label">Natural-language clause</div>
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
                  <span className="dim" style={{ fontSize: 13 }}>
                    Confidence {(rule.extraction.confidence * 100).toFixed(0)}% · mapped to metric <span className="mono">{rule.metric}</span>
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
                <div className="chain__label">Deterministic machine rule</div>
                <MachineRule rule={rule} />
              </div>
              <div className="chain__node">
                <span className="chain__icon">
                  <FileText size={13} />
                </span>
                <div className="chain__label">Evaluated against every bidder</div>
                <div className="grid grid--3" style={{ gap: 8 }}>
                  {results.map(({ v, cell }) => (
                    <div key={v.vendor_id} className="card card--inset" style={{ padding: "10px 12px" }}>
                      <div className="row row--between">
                        <b style={{ fontSize: 13 }}>{v.alias}</b>
                        {cell && <ResultBadge result={cell.result} />}
                      </div>
                      <div className="muted" style={{ fontSize: 12, marginTop: 4, minHeight: 18 }}>
                        {cell?.actual != null ? String(cell.actual) : "no value"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
