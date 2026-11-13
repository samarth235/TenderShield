import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, Download, FileUp, GitBranch, Link2, Play, Scale, TableProperties, Users } from "lucide-react";
import { useRef } from "react";

import { api, openAuthed } from "../api/client";
import type { RestructuringPlan, Scenario } from "../api/types";
import { ErrorCard } from "../components/NotLoaded";
import { Badge, Button, Callout, Card, EmptyState, LoadingBlock, PageHead, StatTile, useToast } from "../components/ui";
import { fmtCr, fmtDateTime } from "../lib/format";
import { useAuth } from "../lib/auth";
import { isNotLoaded, useTender, useTid } from "../lib/hooks";

const SCENARIO_LABEL: Record<string, string> = {
  A_integrated: "A · Current (one contract)",
  B_recommended: "B · Recommended",
  C_max_separation: "C · Maximum separation",
};

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

function FilePicker({ label, accept, busy, onPick }: { label: string; accept: string; busy: boolean; onPick: (f: File) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onPick(f);
          e.target.value = "";
        }}
      />
      <Button type="button" icon={<FileUp size={15} />} loading={busy} onClick={() => ref.current?.click()}>
        {label}
      </Button>
    </>
  );
}

function Inputs({ tid, hasPlan }: { tid: string; hasPlan: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const refresh = () => qc.invalidateQueries({ queryKey: ["tender", tid] });

  const annex = useMutation({
    mutationFn: ({ file, kind }: { file: File; kind: "scope" | "specification" }) => api.uploadTenderDocument(tid, file, kind),
    onSuccess: (r) => { toast(<span>Attached <b>{r.document_id}</b></span>); return refresh(); },
    onError: (e) => toast(<span>Upload failed: {errText(e)}</span>),
  });
  const boq = useMutation({
    mutationFn: (file: File) => api.uploadBoq(tid, file),
    onSuccess: (r) => toast(<span>BOQ loaded: {r.rows} rows{r.total_amount_inr_cr ? `, ${fmtCr(r.total_amount_inr_cr)}` : ""}</span>),
    onError: (e) => toast(<span>BOQ rejected: {errText(e)}</span>),
  });
  const run = useMutation({
    mutationFn: () => api.restructure(tid),
    onSuccess: (plan) => qc.setQueryData(["restructuring", tid], plan),
  });

  return (
    <Card title="Tender inputs" icon={<FileUp size={15} />}>
      <div className="stack">
        <p className="dim" style={{ fontSize: 13 }}>
          Add the parts of the tender bundle that describe the work: Scope of Work, Technical Specifications and the Bill of
          Quantities. The BOQ gives component values; without it values are estimated from the share of scope items.
        </p>
        <div className="row">
          <FilePicker label="Scope of Work (PDF)" accept="application/pdf,.pdf" busy={annex.isPending && annex.variables?.kind === "scope"}
            onPick={(file) => annex.mutate({ file, kind: "scope" })} />
          <FilePicker label="Technical specification (PDF)" accept="application/pdf,.pdf" busy={annex.isPending && annex.variables?.kind === "specification"}
            onPick={(file) => annex.mutate({ file, kind: "specification" })} />
          <FilePicker label="BOQ (CSV / XLSX)" accept=".csv,.xlsx,.xls" busy={boq.isPending} onPick={(file) => boq.mutate(file)} />
        </div>
        <div className="row">
          <Button variant="brand" icon={<Play size={15} />} loading={run.isPending} onClick={() => run.mutate()}>
            {hasPlan ? "Re-run restructuring" : "Run restructuring"}
          </Button>
        </div>
        {run.isError && <Callout tone="danger">{errText(run.error)}</Callout>}
      </div>
    </Card>
  );
}

function ScenarioTable({ plan }: { plan: RestructuringPlan }) {
  const rows = Object.entries(plan.structures.scenarios).filter((e): e is [string, Scenario] => !!e[1]);
  const metricKeys = Array.from(new Set(rows.flatMap(([, s]) => Object.keys(s.metrics))));
  return (
    <Card title="Scenario comparison" icon={<Scale size={15} />} flush>
      <div className="table-scroll"><table className="table">
        <thead>
          <tr>
            <th>Scenario</th>
            <th className="num">Packages</th>
            <th className="num">Score</th>
            {metricKeys.map((k) => <th key={k} className="num">{k.replace(/_/g, " ")}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(([key, s]) => (
            <tr key={key}>
              <td>
                <div style={{ fontWeight: 600 }}>{SCENARIO_LABEL[key] ?? key}</div>
                <div className="muted" style={{ fontSize: 12 }}>{s.summary}</div>
              </td>
              <td className="num mono">{s.n_packages}</td>
              <td className="num mono">{s.score.toFixed(3)}</td>
              {metricKeys.map((k) => {
                const v = s.metrics[k];
                return <td key={k} className="num mono">{v == null ? "—" : Number.isInteger(v) ? v : v.toFixed(2)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table></div>
      <div className="card__body dim" style={{ fontSize: 12.5 }}>
        Robustness: the recommended structure stays best in {pct(plan.structures.sensitivity.recommended_stays_best)} of{" "}
        {plan.structures.sensitivity.draws} weight perturbations ({plan.structures.sensitivity.perturbation}).
        {" "}{plan.structures.feasible_structures} feasible structures were evaluated.
      </div>
    </Card>
  );
}

function PlanView({ plan, tid }: { plan: RestructuringPlan; tid: string }) {
  const toast = useToast();
  const rec = plan.recommendation;
  const labelOf = Object.fromEntries(plan.components.map((c) => [c.component_id, c.label]));
  // The tab must open inside the click, so generation runs inside openAuthed.
  const dossier = useMutation({
    mutationFn: () => openAuthed(async () => { await api.restructuringDossier(tid); return api.restructuringDossierUrl(tid); }),
    onError: (e) => toast(<span>Could not generate the dossier: {errText(e)}</span>),
  });
  const review = plan.relationships.edges.filter((e) => e.review_score >= 0.35);

  return (
    <>
      <Callout tone={plan.structures.recommendation_differs_from_current ? "ok" : undefined}>
        <b>{rec.headline}</b> {rec.decision_note}
      </Callout>

      <div className="grid grid--4">
        <StatTile icon={<Boxes size={14} />} label="Capability components" value={plan.components.length}
          hint={`Estimated value ${fmtCr(plan.estimated_value_inr_cr)}`} />
        <StatTile icon={<TableProperties size={14} />} label="Recommended packages" value={rec.packages.length}
          hint={`${rec.packages.filter((p) => p.sme_size_accessible).length} sized for SMEs`} />
        <StatTile icon={<Users size={14} />} label="Market awards in scope" value={plan.market_scope.awards_in_scope.toLocaleString()}
          hint={plan.market_scope.sources.length ? `${plan.market_scope.sources.length} source(s)` : "No market data loaded"} />
        <StatTile icon={<Link2 size={14} />} label="Relationships to review" value={plan.relationships.requires_review}
          accent={plan.relationships.requires_review ? "var(--high)" : undefined}
          hint={`${plan.relationships.screened_suppliers} shortlisted suppliers screened`} />
      </div>

      {plan.data_quality.filter((d) => d.level === "WARNING").map((d) => (
        <Callout key={d.issue} tone="warn"><b>{d.issue}.</b> {d.fix}.</Callout>
      ))}

      <Card title="Recommended packages" icon={<Boxes size={15} />} flush>
        <div className="table-scroll"><table className="table">
          <thead>
            <tr>
              <th>Package</th>
              <th className="num">Value</th>
              <th className="num">Turnover required</th>
              <th className="num">Capable suppliers</th>
              <th className="num">Meet similar-work scale</th>
              <th className="num">SME candidates</th>
              <th style={{ textAlign: "right" }}>SME accessible</th>
            </tr>
          </thead>
          <tbody>
            {rec.packages.map((p) => (
              <tr key={p.package}>
                <td>
                  <div style={{ fontWeight: 600 }}>{p.package}</div>
                  <div className="muted" style={{ fontSize: 12 }}>{p.scope}</div>
                </td>
                <td className="num mono nowrap">{fmtCr(p.value_inr_cr)}</td>
                <td className="num mono nowrap">{fmtCr(p.required_turnover_cr)}</td>
                <td className="num mono">{p.suppliers_with_full_capability_evidence}</td>
                <td className="num mono">{p.of_which_meet_similar_work_scale}</td>
                <td className="num mono">{p.sme_candidates}</td>
                <td style={{ textAlign: "right" }}>
                  <Badge tone={p.sme_size_accessible ? "pass" : "outline"}>{p.sme_size_accessible ? "Yes" : "No"}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </Card>

      <div className="grid grid--main-side">
        <Card title="Technical dependencies" icon={<GitBranch size={15} />} flush>
          {rec.keep_integrated.length > 0 && (
            <div className="card__body stack" style={{ gap: 8 }}>
              {rec.keep_integrated.map((g) => (
                <div key={g.components.join("+")}>
                  <b>Keep integrated:</b> {g.labels.join(" + ")}
                  <div className="muted" style={{ fontSize: 12 }}>{g.why.join(" ")}</div>
                </div>
              ))}
            </div>
          )}
          <div className="table-scroll"><table className="table">
            <thead>
              <tr><th>Between</th><th>Type</th><th style={{ textAlign: "right" }}>Strength</th></tr>
            </thead>
            <tbody>
              {[...plan.dependency_graph.edges].sort((a, b) => b.weight - a.weight).slice(0, 20).map((e) => (
                <tr key={`${e.source}-${e.target}`} title={e.prior_rationale}>
                  <td>{labelOf[e.source] ?? e.source} ↔ {labelOf[e.target] ?? e.target}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{e.types.join(", ")}</td>
                  <td style={{ textAlign: "right" }}>
                    <Badge tone={e.strength === "strong" ? "high" : "outline"}>{e.strength}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </Card>

        <Card title="Supplier relationships requiring review" icon={<Link2 size={15} />}>
          {review.length === 0 ? (
            <p className="dim" style={{ fontSize: 13 }}>No shortlisted supplier pairs crossed the review threshold.</p>
          ) : (
            <div className="stack" style={{ gap: 10 }}>
              {review.slice(0, 12).map((e) => (
                <div key={`${e.a}-${e.b}`}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{e.a_name ?? e.a} · {e.b_name ?? e.b}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {e.types.join(", ")} · score {e.review_score.toFixed(2)}
                  </div>
                  {e.alternative_explanations.length > 0 && (
                    <div className="dim" style={{ fontSize: 12 }}>Could also be: {e.alternative_explanations.join("; ")}</div>
                  )}
                </div>
              ))}
            </div>
          )}
          <p className="dim" style={{ fontSize: 12, marginTop: 10 }}>{plan.relationships.note}</p>
        </Card>
      </div>

      <ScenarioTable plan={plan} />

      <Card title="Capability components" icon={<TableProperties size={15} />} flush>
        <div className="table-scroll"><table className="table">
          <thead>
            <tr><th>Component</th><th className="num">Items</th><th className="num">Value</th><th>Value basis</th><th className="num">Confidence</th></tr>
          </thead>
          <tbody>
            {plan.components.map((c) => (
              <tr key={c.component_id}>
                <td style={{ fontWeight: 600 }}>{c.label}</td>
                <td className="num mono">{c.n_items}</td>
                <td className="num mono nowrap">{fmtCr(c.value_inr_cr)}</td>
                <td className="muted" style={{ fontSize: 12 }}>{c.value_basis.replace(/_/g, " ")}</td>
                <td className="num mono">{pct(c.mean_confidence)}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </Card>

      <div className="row">
        <Button variant="brand" icon={<Download size={15} />} loading={dossier.isPending} onClick={() => dossier.mutate()}>
          Generate restructuring dossier (PDF)
        </Button>
        <span className="muted" style={{ fontSize: 13 }}>Plan generated {fmtDateTime(plan.generated_at)}</span>
      </div>
    </>
  );
}

export function Restructuring() {
  const tid = useTid();
  const { can } = useAuth();
  const tender = useTender();
  const plan = useQuery({
    queryKey: ["restructuring", tid],
    queryFn: () => api.restructuring(tid),
    enabled: !!tid,
    retry: false,
  });
  if (tender.isLoading) return <LoadingBlock rows={6} />;
  if (tender.error) return <ErrorCard error={tender.error} />;
  const notRun = plan.error && isNotLoaded(plan.error);

  return (
    <>
      <PageHead
        eyebrow={`Tender ${tid} · Restructuring`}
        title={tender.data?.title ?? tid}
        sub="Which parts of this tender can be procured separately so that small and medium enterprises can compete, and which must stay together."
      />
      {can("officer") && <Inputs tid={tid} hasPlan={!!plan.data} />}
      {plan.isLoading && <LoadingBlock rows={6} />}
      {notRun && (
        <Card>
          <EmptyState icon={<Boxes size={30} />} title="No restructuring plan yet">
            Add the scope documents or BOQ above, then run the restructuring analysis.
          </EmptyState>
        </Card>
      )}
      {plan.error && !notRun && <ErrorCard error={plan.error} />}
      {plan.data && <PlanView plan={plan.data} tid={tid} />}
    </>
  );
}
