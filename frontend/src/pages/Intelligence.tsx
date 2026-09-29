import { useQuery } from "@tanstack/react-query";
import { ChevronRight, FileSearch, ListOrdered } from "lucide-react";
import { useState } from "react";

import { api } from "../api/client";
import { ErrorCard, NotLoaded } from "../components/NotLoaded";
import { Badge, Card, DocLink, LoadingBlock, PageHead } from "../components/ui";
import { fmtPct } from "../lib/format";
import { isNotLoaded, TID, useSimilarity, useTender } from "../lib/hooks";

// Same cut-off the backend uses for a "high-overlap" section.
const HIGH_OVERLAP = 0.8;

const simColor = (v: number, median: number) =>
  v >= HIGH_OVERLAP ? "var(--high)" : v > median + 0.1 ? "var(--medium)" : "var(--low)";

export function Intelligence() {
  const sim = useSimilarity();
  const tender = useTender();
  const [picked, setPicked] = useState<[string, string] | null>(null);

  const ranked = [...(sim.data?.pairs ?? [])].sort((x, y) => y.document_similarity - x.document_similarity);
  const pair = picked ?? (ranked[0]?.vendors as [string, string] | undefined);
  const detail = useQuery({
    queryKey: ["sim-pair", TID, pair?.[0], pair?.[1]],
    queryFn: () => api.similarityPair(TID, pair![0], pair![1]),
    enabled: !!pair,
  });

  if (sim.isLoading) return <LoadingBlock rows={8} />;
  if (sim.error) return isNotLoaded(sim.error) ? <NotLoaded what="bid intelligence" /> : <ErrorCard error={sim.error} />;
  if (!pair) return <NotLoaded what="bid intelligence" />;

  const s = sim.data!;
  const bidders = tender.data?.bidders ?? [];
  const alias = (vid: string) => bidders.find((x) => x.vendor_id === vid)?.alias ?? vid;
  const median = s.baseline.median ?? 0;
  const isPicked = (v: [string, string]) => v[0] === pair[0] && v[1] === pair[1];
  const d = detail.data;

  return (
    <>
      <PageHead
        eyebrow="Bid document intelligence"
        title="Proposal similarity"
        sub="Technical proposals are compared pair by pair, at document, section and passage level, against this tender's own baseline. Pairs far above the median deserve a closer read."
        actions={
          <>
            <Badge tone="accent">{s.backend === "tfidf" ? "TF-IDF embeddings" : "Sentence embeddings"}</Badge>
            <Badge tone="outline">median similarity {fmtPct(median)}</Badge>
          </>
        }
      />

      <div className="grid grid--side-main">
        <Card title="Bidder pairs, most similar first" icon={<ListOrdered size={15} />} flush>
          <div className="pair-list">
            {ranked.map((p) => {
              const v = p.document_similarity;
              return (
                <button key={p.vendors.join()} className={`pair-item${isPicked(p.vendors) ? " active" : ""}`} onClick={() => setPicked(p.vendors)}>
                  <span className="pair-item__name">
                    {alias(p.vendors[0])} ↔ {alias(p.vendors[1])}
                  </span>
                  <span className="pair-item__pct" style={{ color: simColor(v, median) }}>
                    {Math.round(v * 100)}%
                  </span>
                  <span className="bar">
                    <span className="bar__fill" style={{ width: `${v * 100}%`, background: simColor(v, median) }} />
                    <span className="bar__median" style={{ left: `${median * 100}%` }} />
                  </span>
                </button>
              );
            })}
          </div>
          <p className="muted" style={{ fontSize: 12, padding: "10px 16px", borderTop: "1px solid var(--line)" }}>
            Dark marker = tender median ({fmtPct(median)}). Red = at or above {Math.round(HIGH_OVERLAP * 100)}% similarity.
          </p>
        </Card>

        <Card
          title={`${alias(pair[0])} ↔ ${alias(pair[1])}`}
          icon={<FileSearch size={15} />}
          actions={
            d && (
              <span className="row" style={{ gap: 6 }}>
                <DocLink documentId={d.documents[0]} label={d.filenames[0]} />
                <DocLink documentId={d.documents[1]} label={d.filenames[1]} />
              </span>
            )
          }
        >
          {detail.isLoading && <LoadingBlock />}
          {d && (
            <div className="stack" style={{ gap: 20 }}>
              <div className="sim-score">
                <span className="sim-score__value" style={{ color: simColor(d.document_similarity, median) }}>
                  {fmtPct(d.document_similarity)}
                </span>
                <span>
                  overall similarity ·{" "}
                  {median > 0 ? (
                    <b>
                      {d.document_similarity >= median ? "+" : "−"}
                      {Math.abs(Math.round((d.document_similarity - median) * 100))} pts vs median
                    </b>
                  ) : null}
                </span>
              </div>

              <div className="stack stack--sm">
                <div className="section-label">Similarity by section</div>
                {d.sections.map((sec) => (
                  <div key={sec.title} className="bar-row">
                    <span>{sec.title}</span>
                    <div className="bar">
                      <div className="bar__fill" style={{ width: `${sec.similarity * 100}%`, background: simColor(sec.similarity, median) }} />
                    </div>
                    <span className="mono" style={{ textAlign: "right" }}>
                      {Math.round(sec.similarity * 100)}%
                    </span>
                  </div>
                ))}
              </div>

              {d.passages.length === 0 ? (
                <p className="muted">No passage-level matches above the 75% threshold. The proposals are written differently.</p>
              ) : (
                <details className="disclosure" key={pair.join()}>
                  <summary>
                    <ChevronRight size={14} className="disclosure__chev" />
                    Matching passages
                    <Badge tone="outline">{d.passages.length}</Badge>
                    <span className="disclosure__hint" />
                  </summary>
                  <div className="disclosure__body">
                    {d.passages.map((p, i) => (
                      <div key={i} className="passage">
                        <div>
                          <div className="passage__meta">
                            <span>
                              {alias(pair[0])} · {p.section} · p.{p.a.page}
                            </span>
                            <span className="mono">{Math.round(p.similarity * 100)}%</span>
                          </div>
                          {p.a.text}
                        </div>
                        <div>
                          <div className="passage__meta">
                            <span>
                              {alias(pair[1])} · p.{p.b.page}
                            </span>
                          </div>
                          {p.b.text}
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
