import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import { Network, Route, Waypoints } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { GraphNode, GraphView, RelationshipPath } from "../api/types";
import { ErrorCard, NotLoaded } from "../components/NotLoaded";
import { Badge, Button, Card, LevelBadge, LoadingBlock, PageHead, Switch } from "../components/ui";
import { humanize } from "../lib/format";
import { isNotLoaded, TID, useFindings, useGraph, useTender } from "../lib/hooks";

const cssVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";

type Toggles = { tenders: boolean; documents: boolean; contacts: boolean };

function buildElements(view: GraphView, toggles: Toggles, levels: Record<string, string>): ElementDefinition[] {
  const hidden = new Set<string>();
  view.nodes.forEach((n) => {
    if ((n.type === "tender" && !toggles.tenders && !n.is_current) || (n.type === "document" && !toggles.documents) || (n.type === "contact" && !toggles.contacts))
      hidden.add(n.id);
    if (n.type === "tender" && n.is_current && !toggles.tenders) hidden.add(n.id);
  });
  const nodes: ElementDefinition[] = view.nodes
    .filter((n) => !hidden.has(n.id))
    .map((n) => ({
      data: {
        ...n,
        id: n.id,
        label: n.type === "address" ? String(n.label).split(",").slice(0, 2).join(",") : String(n.label),
        level: n.type === "vendor" ? levels[String(n.vendor_id)] ?? "NONE" : "NONE",
      },
      classes: [n.type, n.is_current ? "current" : "", n.type === "vendor" && levels[String(n.vendor_id)] ? `lvl-${levels[String(n.vendor_id)]}` : ""].join(" "),
    }));
  const edges: ElementDefinition[] = view.edges
    .filter((e) => !hidden.has(e.source) && !hidden.has(e.target))
    .filter((e) => e.type !== "PARTICIPATED_IN" || toggles.tenders)
    .map((e) => ({
      data: {
        ...e,
        id: e.id,
        label: e.type === "CO_BID" ? `${e.weight}×` : e.type === "SIMILAR_TO" ? `${Math.round(Number(e.score) * 100)}%` : "",
        weight: Number(e.weight ?? 1),
      },
      classes: e.type,
    }));
  return [...nodes, ...edges];
}

function style(): cytoscape.StylesheetJson {
  const ink = cssVar("--ink");
  const ink3 = cssVar("--ink-3");
  const surface = cssVar("--surface");
  return [
    {
      selector: "node",
      style: {
        label: "data(label)",
        "font-family": "IBM Plex Sans, sans-serif",
        "font-size": 10,
        color: ink,
        "text-valign": "bottom",
        "text-margin-y": 5,
        "text-wrap": "ellipsis",
        "text-max-width": "120px",
        "border-width": 2,
        "border-color": surface,
        "overlay-opacity": 0,
      },
    },
    {
      selector: "node.vendor",
      style: {
        shape: "round-rectangle",
        width: 58,
        height: 34,
        "background-color": cssVar("--chrome"),
        color: "#fff",
        "text-valign": "center",
        "text-margin-y": 0,
        "font-size": 11,
        "font-weight": 600,
      },
    },
    { selector: "node.vendor[?is_bidder]", style: { width: 76, height: 38, "font-size": 12 } },
    { selector: "node.lvl-HIGH", style: { "border-color": cssVar("--high"), "border-width": 4 } },
    { selector: "node.lvl-MEDIUM", style: { "border-color": cssVar("--medium"), "border-width": 4 } },
    { selector: "node.lvl-LOW", style: { "border-color": cssVar("--low"), "border-width": 3 } },
    { selector: "node.lvl-FAIL", style: { "border-color": cssVar("--fail"), "border-width": 3 } },
    { selector: "node.lvl-INSUFFICIENT_DATA", style: { "border-color": cssVar("--unknown"), "border-width": 3, "border-style": "dashed" } },
    { selector: "node.director", style: { shape: "ellipse", width: 24, height: 24, "background-color": cssVar("--fam-corporate") } },
    { selector: "node.address", style: { shape: "diamond", width: 26, height: 26, "background-color": cssVar("--fam-document") } },
    { selector: "node.contact", style: { shape: "triangle", width: 18, height: 18, "background-color": ink3 } },
    { selector: "node.tender", style: { shape: "rectangle", width: 12, height: 12, "background-color": ink3, "font-size": 8, color: ink3 } },
    { selector: "node.tender.current", style: { width: 26, height: 26, shape: "star", "background-color": cssVar("--brand"), color: ink, "font-size": 10 } },
    { selector: "node.document", style: { shape: "round-tag", width: 16, height: 20, "background-color": cssVar("--surface-3"), "border-color": ink3, "border-width": 1, "font-size": 8 } },
    {
      selector: "edge",
      style: {
        width: 1.5,
        "line-color": cssVar("--line-strong"),
        "curve-style": "bezier",
        label: "data(label)",
        "font-size": 9,
        "font-family": "IBM Plex Mono, monospace",
        color: ink,
        "text-background-color": surface,
        "text-background-opacity": 1,
        "text-background-padding": "2px",
        "overlay-opacity": 0,
      },
    },
    { selector: "edge.DIRECTED_BY", style: { "line-color": cssVar("--fam-corporate"), width: 2 } },
    { selector: "edge.REGISTERED_AT", style: { "line-color": cssVar("--fam-document"), width: 2 } },
    { selector: "edge.USES_CONTACT", style: { "line-color": ink3 } },
    { selector: "edge.PARTICIPATED_IN", style: { "line-color": cssVar("--line"), width: 1 } },
    { selector: "edge.WON", style: { "line-color": cssVar("--brand"), width: 1.5, "line-style": "dashed" } },
    { selector: "edge.SUBMITTED", style: { "line-color": cssVar("--line-strong"), "line-style": "dotted" } },
    { selector: "edge.SIMILAR_TO", style: { "line-color": cssVar("--fam-document"), width: 3, "line-style": "dashed" } },
    {
      selector: "edge.CO_BID",
      style: {
        "line-color": cssVar("--fam-behavioural"),
        width: "mapData(weight, 0, 5, 1, 7)",
        opacity: 0.75,
        "curve-style": "unbundled-bezier",
      },
    },
    { selector: ".faded", style: { opacity: 0.12 } },
    { selector: "node.hl", style: { "border-color": cssVar("--brand"), "border-width": 5, opacity: 1 } },
    { selector: "edge.hl", style: { "line-color": cssVar("--brand"), width: 4, opacity: 1 } },
    { selector: "node:selected", style: { "border-color": cssVar("--accent"), "border-width": 5 } },
  ];
}

export function GraphPage() {
  const graph = useGraph();
  const tender = useTender();
  const findings = useFindings();
  const [params] = useSearchParams();
  const container = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [toggles, setToggles] = useState<Toggles>({ tenders: false, documents: false, contacts: false });
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [neighbours, setNeighbours] = useState<GraphNode[]>([]);
  const [pair, setPair] = useState<[string, string]>(["V001", "V002"]);
  const [paths, setPaths] = useState<RelationshipPath[] | null>(null);

  const levels = useMemo(() => {
    const rank = ["LOW", "INSUFFICIENT_DATA", "FAIL", "MEDIUM", "HIGH"];
    const out: Record<string, string> = {};
    findings.data?.forEach((f) =>
      f.subject.vendors.forEach((v) => {
        if (rank.indexOf(f.level) > rank.indexOf(out[v.vendor_id] ?? "")) out[v.vendor_id] = f.level;
      }),
    );
    return out;
  }, [findings.data]);

  useEffect(() => {
    if (!graph.data || !container.current) return;
    const cy = cytoscape({
      container: container.current,
      elements: buildElements(graph.data, toggles, levels),
      style: style(),
      layout: { name: "cose", animate: false, nodeRepulsion: () => 90000, idealEdgeLength: () => 90, gravity: 0.35, padding: 40, randomize: false } as cytoscape.LayoutOptions,
      wheelSensitivity: 0.25,
      minZoom: 0.2,
      maxZoom: 3,
    });
    cy.on("tap", "node", (evt) => {
      const n = evt.target;
      setSelected(n.data() as GraphNode);
      setNeighbours(n.neighborhood("node").map((x: cytoscape.NodeSingular) => x.data() as GraphNode));
      cy.elements().addClass("faded");
      n.closedNeighborhood().removeClass("faded");
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        cy.elements().removeClass("faded hl");
        setSelected(null);
      }
    });
    cyRef.current = cy;
    const focus = params.get("focus");
    if (focus) cy.getElementById(`vendor:${focus}`).emit("tap");
    return () => cy.destroy();
  }, [graph.data, toggles, levels, params]);

  const explain = async () => {
    const res = await api.paths(TID, pair[0], pair[1]);
    setPaths(res.paths);
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().removeClass("hl").addClass("faded");
    const a = cy.getElementById(`vendor:${pair[0]}`);
    const b = cy.getElementById(`vendor:${pair[1]}`);
    a.add(b).removeClass("faded").addClass("hl");
    res.paths.forEach((p) => {
      const mid = cy.getElementById(p.via.id);
      mid.removeClass("faded").addClass("hl");
      mid.edgesWith(a.add(b)).removeClass("faded").addClass("hl");
    });
    a.edgesWith(b).removeClass("faded").addClass("hl");
  };

  if (graph.isLoading) return <LoadingBlock rows={8} />;
  if (graph.error) return isNotLoaded(graph.error) ? <NotLoaded what="relationship graph" /> : <ErrorCard error={graph.error} />;
  const bidders = tender.data?.bidders ?? [];

  return (
    <>
      <PageHead
        step="02"
        eyebrow="Procurement relationship graph"
        title="Who is connected to whom"
        sub="Vendors, directors, registered premises, contacts, tenders and documents in one multi-relational graph. Co-bidding edges get thicker the more often two bidders have bid in the same tenders. Borders show each vendor's strongest finding."
      />
      <div className="grid grid--main-side">
        <div className="stack">
          <div className="row row--between">
            <div className="graph-legend">
              <span><span className="graph-legend__shape" style={{ background: "var(--chrome)", borderRadius: 3, outline: "1px solid var(--line-strong)" }} />Vendor</span>
              <span><span className="graph-legend__shape" style={{ background: "var(--fam-corporate)", borderRadius: "50%" }} />Director</span>
              <span><span className="graph-legend__shape" style={{ background: "var(--fam-document)", transform: "rotate(45deg) scale(.8)" }} />Address</span>
              <span><span className="graph-legend__shape" style={{ background: "var(--fam-behavioural)", height: 4 }} />Co-bidding</span>
              <span><span className="graph-legend__shape" style={{ background: "var(--brand)", clipPath: "polygon(50% 0,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%)" }} />Current tender</span>
            </div>
            <div className="row" style={{ fontSize: 12.5 }}>
              {(["tenders", "documents", "contacts"] as const).map((k) => (
                <label key={k} className="row" style={{ gap: 6, cursor: "pointer" }}>
                  <Switch checked={toggles[k]} onChange={(v) => setToggles((t) => ({ ...t, [k]: v }))} label={`Show ${k}`} />
                  {humanize(k)}
                </label>
              ))}
            </div>
          </div>
          <div ref={container} className="graph-canvas" />
        </div>

        <div className="stack">
          <Card title="Explain a relationship" icon={<Route size={15} />}>
            <div className="stack">
              <div className="row" style={{ flexWrap: "nowrap" }}>
                {[0, 1].map((i) => (
                  <select
                    key={i}
                    className="select"
                    value={pair[i]}
                    onChange={(e) => setPair((p) => (i === 0 ? [e.target.value, p[1]] : [p[0], e.target.value]))}
                  >
                    {bidders.map((b) => (
                      <option key={b.vendor_id} value={b.vendor_id}>
                        {b.alias}
                      </option>
                    ))}
                  </select>
                ))}
              </div>
              <Button variant="primary" icon={<Waypoints size={15} />} onClick={explain} disabled={pair[0] === pair[1]}>
                Trace connection
              </Button>
              {paths && paths.length === 0 && <p className="muted">No shared director, address, contact or tender links these two vendors.</p>}
              {paths && paths.length > 0 && (
                <div>
                  {paths.map((p) => (
                    <div key={p.via.id} className="path-row">
                      <Badge tone={p.via.type === "tender" ? "outline" : p.via.type === "director" ? "accent" : "brand"}>{p.via.type}</Badge>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13 }}>{p.via.label}</div>
                        <div className="muted mono" style={{ fontSize: 11 }}>
                          {p.edges.join(" · ")}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>

          <Card title={selected ? humanize(selected.type) : "Node details"} icon={<Network size={15} />}>
            {!selected && <p className="muted">Click a node to inspect it and highlight its neighbourhood.</p>}
            {selected && (
              <div className="stack">
                <div>
                  <h3 style={{ fontSize: 16 }}>{String(selected.label)}</h3>
                  {selected.type === "vendor" && <p className="muted">{String(selected.name)}</p>}
                </div>
                {selected.type === "vendor" && (
                  <div className="row">
                    {selected.is_bidder ? <Badge tone="brand">Bidder on {TID}</Badge> : <Badge tone="outline">Registry vendor</Badge>}
                    {levels[String(selected.vendor_id)] && <LevelBadge level={levels[String(selected.vendor_id)]} />}
                    {selected.directors_available === false && <Badge tone="unknown">Directors unavailable</Badge>}
                  </div>
                )}
                {selected.type === "director" && selected.din ? <p className="mono dim">DIN {String(selected.din)}</p> : null}
                <div>
                  <div className="section-label" style={{ marginBottom: 6 }}>
                    Connected ({neighbours.length})
                  </div>
                  <div className="stack stack--sm" style={{ maxHeight: 260, overflow: "auto" }}>
                    {neighbours.map((n) => (
                      <div key={n.id} className="row row--between" style={{ fontSize: 13 }}>
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 230 }}>{String(n.label)}</span>
                        <Badge tone="outline">{n.type}</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </Card>

          <Card title="Graph size">
            <div className="grid grid--2" style={{ gap: 10, fontSize: 13 }}>
              {Object.entries(graph.data!.stats.nodes).map(([k, v]) => (
                <div key={k} className="row row--between">
                  <span className="muted">{humanize(k)}s</span>
                  <b className="mono">{v}</b>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
