import { useQuery } from "@tanstack/react-query";
import { Activity, Check, FileSearch, Minus } from "lucide-react";
import { useState } from "react";

import { api } from "../api/client";
import { ErrorCard, NotLoaded } from "../components/NotLoaded";
import { Badge, Card, DocLink, LoadingBlock, PageHead } from "../components/ui";
import { fmtPct } from "../lib/format";
import { isNotLoaded, TID, useBehaviour, useSimilarity, useTender } from "../lib/hooks";

function heat(v: number, median: number) {
  // Colour relative to the tender's own baseline: at/below median is neutral, far above is hot.
  const t = Math.max(0, Math.min(1, (v - median) / Math.max(0.0001, 1 - median)));
  const mix = Math.round(8 + t * 92);
  return { background: `color-mix(in srgb, var(--high) ${mix}%, var(--surface-3))`, color: t > 0.45 ? "#fff" : "var(--ink)" };
}

const FLAGS: { key: string; label: string }[] = [
  { key: "repeated_co_bidding", label: "Co-bid" },
  { key: "winner_rotation", label: "Rotation" },
  { key: "price_proximity", label: "Price" },
  { key: "submission_timing", label: "Timing" },
];

export function Intelligence() {
  const sim = useSimilarity();
  const beh = useBehaviour();
  const tender = useTender();
  const [pair, setPair] = useState<[string, string]>(["V001", "V002"]);
  const detail = useQuery({
    queryKey: ["sim-pair", TID, pair[0], pair[1]],
    queryFn: () => api.similarityPair(TID, pair[0], pair[1]),
    enabled: !!sim.data,
  });

  if (sim.isLoading || beh.isLoading) return <LoadingBlock rows={8} />;
  const err = sim.error ?? beh.error;
  if (err) return isNotLoaded(err) ? <NotLoaded what="bid intelligence" /> : <ErrorCard error={err} />;

  const s = sim.data!;
  const b = beh.data!;
  const bidders = tender.data?.bidders ?? [];
  const alias = (vid: string) => bidders.find((x) => x.vendor_id === vid)?.alias ?? vid;
  const median = s.baseline.median ?? 0;
  const lookup = (a: string, c: string) =>
    s.pairs.find((p) => (p.vendors[0] === a && p.vendors[1] === c) || (p.vendors[0] === c && p.vendors[1] === a));

  return (
    <>
      <PageHead
        step="04"
        eyebrow="Bid document + behaviour intelligence"
        title="Signals from documents and bidding history"
        sub="Semantic similarity between technical proposals is measured at document, section and passage level against this tender's own baseline. Historical behaviour is scored with transparent thresholds and an Isolation Forest."
        actions={
          <>
            <Badge tone="accent">{s.backend === "tfidf" ? "TF-IDF embeddings" : "Sentence embeddings"}</Badge>
            <Badge tone="outline">median similarity {fmtPct(median)}</Badge>
          </>
        }
      />

      <div className="grid" style={{ gridTemplateColumns: "minmax(320px, 420px) minmax(0, 1fr)", alignItems: "start" }}>
        <Card title="Proposal similarity" icon={<FileSearch size={15} />}>
          <div className="heatmap" style={{ gridTemplateColumns: `36px repeat(${bidders.length}, 1fr)` }}>
            <span />
            {bidders.map((v) => (
              <span key={v.vendor_id} className="heatmap__label">
                {v.alias?.split(" ").pop()}
              </span>
            ))}
            {bidders.map((row) => [
              <span key={`l-${row.vendor_id}`} className="heatmap__label">
                {row.alias?.split(" ").pop()}
              </span>,
              ...bidders.map((col) => {
                if (row.vendor_id === col.vendor_id)
                  return <span key={col.vendor_id} className="heatmap__cell" style={{ background: "var(--surface-3)", cursor: "default" }} />;
                const p = lookup(row.vendor_id, col.vendor_id);
                const v = p?.document_similarity ?? 0;
                const isSel = (pair[0] === row.vendor_id && pair[1] === col.vendor_id) || (pair[1] === row.vendor_id && pair[0] === col.vendor_id);
                return (
                  <button
                    key={col.vendor_id}
                    className={`heatmap__cell${isSel ? " selected" : ""}`}
                    style={heat(v, median)}
                    onClick={() => setPair([row.vendor_id, col.vendor_id].sort() as [string, string])}
                    title={`${row.alias} ↔ ${col.alias}: ${fmtPct(v)}`}
                  >
                    {Math.round(v * 100)}
                  </button>
                );
              }),
            ])}
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
            Cell = % semantic similarity of technical proposals. Colour intensity is relative to the tender median ({fmtPct(median)}). Click a cell to compare.
          </p>
        </Card>

        <Card
          title={
            <>
              {alias(pair[0])} ↔ {alias(pair[1])}
            </>
          }
          actions={detail.data && <b style={{ fontSize: 22, letterSpacing: "-0.02em" }}>{fmtPct(detail.data.document_similarity)}</b>}
        >
          {detail.isLoading && <LoadingBlock />}
          {detail.data && (
            <div className="stack">
              <div className="stack stack--sm">
                <div className="section-label">Section-level similarity</div>
                {detail.data.sections.map((sec) => (
                  <div key={sec.title} className="bar-row">
                    <span>{sec.title}</span>
                    <div className="bar">
                      <div
                        className="bar__fill"
                        style={{ width: `${sec.similarity * 100}%`, background: sec.similarity >= 0.8 ? "var(--high)" : "var(--low)" }}
                      />
                    </div>
                    <span className="mono" style={{ textAlign: "right" }}>
                      {Math.round(sec.similarity * 100)}%
                    </span>
                  </div>
                ))}
              </div>
              <div className="stack stack--sm">
                <div className="row row--between">
                  <span className="section-label">Matching passages ({detail.data.passages.length})</span>
                  <span className="row">
                    <DocLink documentId={detail.data.documents[0]} label={detail.data.filenames[0]} />
                    <DocLink documentId={detail.data.documents[1]} label={detail.data.filenames[1]} />
                  </span>
                </div>
                {detail.data.passages.length === 0 && <p className="muted">No passage-level matches above the 75% threshold. The proposals are written differently.</p>}
                {detail.data.passages.slice(0, 5).map((p, i) => (
                  <div key={i} className="passage">
                    <div>
                      <div className="passage__meta">
                        <span>{alias(pair[0])} · {p.section} · p.{p.a.page}</span>
                        <span className="mono">{Math.round(p.similarity * 100)}%</span>
                      </div>
                      {p.a.text}
                    </div>
                    <div>
                      <div className="passage__meta">
                        <span>{alias(pair[1])} · p.{p.b.page}</span>
                      </div>
                      {p.b.text}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      <Card
        title="Bidding behaviour across historical tenders"
        icon={<Activity size={15} />}
        flush
        actions={
          b.model.trained ? (
            <Badge tone="accent">
              {b.model.type} · {b.model.training_pairs} pairs · {b.model.outliers} outliers
            </Badge>
          ) : null
        }
      >
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>Pair</th>
                <th className="num">Common tenders</th>
                <th className="num">Expected</th>
                <th className="num">Win/runner-up</th>
                <th className="num">Price gap</th>
                <th className="num">Submission gap</th>
                {FLAGS.map((f) => (
                  <th key={f.key} style={{ textAlign: "center" }}>
                    {f.label}
                  </th>
                ))}
                <th className="num">Anomaly rank</th>
              </tr>
            </thead>
            <tbody>
              {[...b.pairs]
                .sort((x, y) => (x.anomaly?.rank ?? 1e9) - (y.anomaly?.rank ?? 1e9))
                .map((p) => {
                  const hot = Object.values(p.flags).filter(Boolean).length;
                  return (
                    <tr key={p.vendors.join()} style={hot >= 3 ? { background: "var(--high-soft)" } : undefined}>
                      <td style={{ fontWeight: 600 }}>
                        {alias(p.vendors[0])} ↔ {alias(p.vendors[1])}
                      </td>
                      <td className="num mono">{p.co_bids}</td>
                      <td className="num mono muted">{p.expected_co_bids.toFixed(1)}</td>
                      <td className="num mono">{p.rotation_count}</td>
                      <td className="num mono">{fmtPct(p.price_gap_median)}</td>
                      <td className="num mono">{p.submission_gap_median_min == null ? "—" : `${Math.round(p.submission_gap_median_min)} min`}</td>
                      {FLAGS.map((f) => (
                        <td key={f.key} style={{ textAlign: "center" }}>
                          <span className={`flag ${p.flags[f.key] ? "flag--on" : "flag--off"}`}>
                            {p.flags[f.key] ? <Check size={13} strokeWidth={3} /> : <Minus size={12} />}
                          </span>
                        </td>
                      ))}
                      <td className="num">
                        {p.anomaly ? (
                          <span className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                            <span className="mono">#{p.anomaly.rank}</span>
                            {p.anomaly.is_outlier && <Badge tone="high">outlier</Badge>}
                          </span>
                        ) : (
                          <span className="muted">never co-bid</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
