import { ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ErrorCard, NotLoaded } from "../components/NotLoaded";
import { Badge, Card, LevelBadge, LoadingBlock, PageHead } from "../components/ui";
import { CATEGORY_LABEL, humanize, prettyTitle } from "../lib/format";
import { isNotLoaded, useFindings } from "../lib/hooks";

const TABS = [
  { key: "ALL", label: "All" },
  { key: "INVESTIGATION_SIGNAL", label: "Investigation signals" },
  { key: "COMPLIANCE", label: "Compliance" },
  { key: "DATA_QUALITY", label: "Data quality" },
];

export function Findings() {
  const q = useFindings();
  const [tab, setTab] = useState("ALL");

  if (q.isLoading) return <LoadingBlock rows={6} />;
  if (q.error) return isNotLoaded(q.error) ? <NotLoaded what="findings" /> : <ErrorCard error={q.error} />;
  const all = q.data!;
  if (!all.length) return <NotLoaded what="findings" />;
  const shown = tab === "ALL" ? all : all.filter((f) => f.category === tab);

  return (
    <>
      <PageHead
        eyebrow="Evidence reasoning engine"
        title="Findings"
        sub="Results are kept in three separate categories: objective compliance results, patterns that deserve human examination, and gaps in the evidence. A relationship alone is never treated as proof of misconduct."
      />
      <div className="row">
        {TABS.map((t) => {
          const n = t.key === "ALL" ? all.length : all.filter((f) => f.category === t.key).length;
          return (
            <button key={t.key} className={`btn btn--sm${tab === t.key ? " btn--primary" : ""}`} onClick={() => setTab(t.key)}>
              {t.label}
              <span className="mono" style={{ opacity: 0.7 }}>{n}</span>
            </button>
          );
        })}
      </div>
      <Card flush title={`${shown.length} findings`} icon={<ShieldAlert size={15} />}>
        {shown.map((f) => (
          <Link key={f.finding_id} to={`/findings/${f.finding_id}`} className="finding-row">
            <span className={`finding-row__rail rail--${f.level}`} />
            <div>
              <div className="finding-row__title">{prettyTitle(f.title)}</div>
              <div className="finding-row__meta">
                <span className="mono">{f.finding_id}</span>
                <span>{CATEGORY_LABEL[f.category]}</span>
                <span>{f.evidence_count} evidence items</span>
                <span>data quality {f.data_quality.toLowerCase()}</span>
                <Badge tone="outline">{humanize(f.recommendation)}</Badge>
              </div>
            </div>
            <div className="row">
              <LevelBadge level={f.level} />
            </div>
          </Link>
        ))}
      </Card>
    </>
  );
}
