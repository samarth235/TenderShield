"""Procurement Relationship Graph (Stage 6) built with NetworkX.

Nodes: vendor, director, address, contact, tender, document.
Edges: DIRECTED_BY, REGISTERED_AT, USES_CONTACT, PARTICIPATED_IN, WON, SUBMITTED, SIMILAR_TO,
       plus the derived CO_BID projection between vendors that bid in the same tenders.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations

import networkx as nx

from ..db import fetch_all, get_artifact, put_artifact

CORPORATE_EDGES = {"DIRECTED_BY", "REGISTERED_AT", "USES_CONTACT"}
SIMILARITY_EDGE_THRESHOLD = 0.7


def _vendor_node(vid: str) -> str:
    return f"vendor:{vid}"


def build_graph(conn: sqlite3.Connection, tender_id: str) -> nx.MultiGraph:
    entities = get_artifact(conn, tender_id, "entities")
    if entities is None:
        raise LookupError("Run entity resolution before building the graph.")
    similarity = get_artifact(conn, tender_id, "similarity") or {"pairs": []}

    g = nx.MultiGraph()
    bidders = {r["vendor_id"] for r in fetch_all(
        conn, "SELECT vendor_id FROM bids WHERE tender_id = ? AND vendor_id IS NOT NULL", (tender_id,))}
    for v in fetch_all(conn, "SELECT vendor_id, alias, name, directors FROM vendors"):
        g.add_node(_vendor_node(v["vendor_id"]), type="vendor", label=v["alias"] or v["name"], name=v["name"],
                   vendor_id=v["vendor_id"], is_bidder=v["vendor_id"] in bidders,
                   directors_available=bool(v["directors"]))

    for ent in entities["entities"]["directors"]:
        node = f"director:{ent['entity_id']}"
        g.add_node(node, type="director", label=ent["name"], din=ent["din"])
        for r in ent["records"]:
            g.add_edge(_vendor_node(r["vendor_id"]), node, key="DIRECTED_BY", type="DIRECTED_BY", raw_name=r["raw_name"])
    for ent in entities["entities"]["addresses"]:
        node = f"address:{ent['entity_id']}"
        g.add_node(node, type="address", label=ent["records"][0]["raw"], pincode=ent["pincode"])
        for r in ent["records"]:
            g.add_edge(_vendor_node(r["vendor_id"]), node, key="REGISTERED_AT", type="REGISTERED_AT", raw=r["raw"])
    for ent in entities["entities"]["contacts"]:
        node = f"contact:{ent['entity_id']}"
        g.add_node(node, type="contact", label=ent["value"], kind=ent["kind"])
        for r in ent["records"]:
            g.add_edge(_vendor_node(r["vendor_id"]), node, key="USES_CONTACT", type="USES_CONTACT", raw=r["raw"])

    for t in fetch_all(conn, "SELECT tender_id, title, status, is_current, bid_deadline FROM tenders"):
        g.add_node(f"tender:{t['tender_id']}", type="tender", label=t["tender_id"], title=t["title"],
                   status=t["status"], is_current=bool(t["is_current"]), date=(t["bid_deadline"] or "")[:10])
    for b in fetch_all(conn, "SELECT tender_id, vendor_id, outcome, amount_cr, rank FROM bids WHERE vendor_id IS NOT NULL"):
        vnode, tnode = _vendor_node(b["vendor_id"]), f"tender:{b['tender_id']}"
        g.add_edge(vnode, tnode, key="PARTICIPATED_IN", type="PARTICIPATED_IN", outcome=b["outcome"],
                   amount_cr=b["amount_cr"], rank=b["rank"])
        if b["outcome"] == "WON":
            g.add_edge(vnode, tnode, key="WON", type="WON", amount_cr=b["amount_cr"])

    for d in fetch_all(conn, "SELECT document_id, vendor_id, kind, filename FROM documents WHERE tender_id = ?", (tender_id,)):
        node = f"document:{d['document_id']}"
        g.add_node(node, type="document", label=d["filename"], kind=d["kind"])
        if d["vendor_id"]:
            g.add_edge(_vendor_node(d["vendor_id"]), node, key="SUBMITTED", type="SUBMITTED")
        else:
            g.add_edge(f"tender:{tender_id}", node, key="SUBMITTED", type="SUBMITTED")
    for pair in similarity["pairs"]:
        if pair["document_similarity"] >= SIMILARITY_EDGE_THRESHOLD:
            g.add_edge(f"document:{pair['documents'][0]}", f"document:{pair['documents'][1]}", key="SIMILAR_TO",
                       type="SIMILAR_TO", score=pair["document_similarity"])
    return g


def co_bid_counts(g: nx.MultiGraph, vendor_ids: list[str] | None = None, exclude_tender: str | None = None) -> Counter:
    """Counter over (vendor_a, vendor_b) of tenders both participated in."""
    counts: Counter = Counter()
    for node, data in g.nodes(data=True):
        if data.get("type") != "tender" or node == f"tender:{exclude_tender}":
            continue
        participants = sorted({
            g.nodes[n]["vendor_id"] for n in g.neighbors(node)
            if g.nodes[n].get("type") == "vendor" and g.has_edge(n, node, key="PARTICIPATED_IN")
        })
        if vendor_ids is not None:
            participants = [p for p in participants if p in vendor_ids]
        for a, b in combinations(participants, 2):
            counts[(a, b)] += 1
    return counts


def _serialise(g: nx.MultiGraph, nodes: set[str], extra_edges: list[dict] | None = None) -> dict:
    out_nodes = [{"id": n, **{k: v for k, v in g.nodes[n].items()}} for n in sorted(nodes)]
    out_edges = []
    for u, v, key, data in g.edges(keys=True, data=True):
        if u in nodes and v in nodes:
            a, b = sorted((u, v))
            out_edges.append({"id": f"{a}|{key}|{b}", "source": a, "target": b, **data})
    out_edges.extend(extra_edges or [])
    type_counts = Counter(n["type"] for n in out_nodes)
    edge_counts = Counter(e["type"] for e in out_edges)
    return {"nodes": out_nodes, "edges": out_edges, "stats": {"nodes": dict(type_counts), "edges": dict(edge_counts)}}


def tender_view(g: nx.MultiGraph, tender_id: str) -> dict:
    """Bidders of the tender, their corporate entities and second-degree corporate network,
    shared-history tenders and bid documents."""
    tnode = f"tender:{tender_id}"
    bidders = sorted(n for n in g.neighbors(tnode) if g.nodes[n].get("type") == "vendor")
    bidder_ids = [g.nodes[n]["vendor_id"] for n in bidders]
    nodes = {tnode, *bidders}
    corporate = ("director", "address", "contact")
    for b in bidders:
        for n in g.neighbors(b):
            if g.nodes[n]["type"] in (*corporate, "document"):
                nodes.add(n)
    # Registry vendors tied to a bidder through a director, address or contact, and the
    # corporate records they share with each other - the second-degree network.
    related = {m for n in list(nodes) if g.nodes[n]["type"] in corporate for m in g.neighbors(n)
               if g.nodes[m]["type"] == "vendor" and m not in bidders}
    circle = set(bidders) | related
    nodes |= related
    for v in related:
        for n in g.neighbors(v):
            if g.nodes[n]["type"] in corporate and sum(m in circle for m in g.neighbors(n)) >= 2:
                nodes.add(n)
    # Historical tenders where at least two current bidders met.
    for n, data in g.nodes(data=True):
        if data.get("type") == "tender" and n != tnode:
            met = [b for b in bidders if g.has_edge(b, n, key="PARTICIPATED_IN")]
            if len(met) >= 2:
                nodes.add(n)
    co_bids = co_bid_counts(g, bidder_ids, exclude_tender=tender_id)
    extra = [
        {"id": f"vendor:{a}|CO_BID|vendor:{b}", "source": f"vendor:{a}", "target": f"vendor:{b}", "type": "CO_BID",
         "derived": True, "weight": count}
        for (a, b), count in sorted(co_bids.items())
    ]
    return _serialise(g, nodes, extra)


def vendor_view(g: nx.MultiGraph, vendor_id: str, depth: int = 2, max_nodes: int = 150) -> dict:
    center = _vendor_node(vendor_id)
    if center not in g:
        raise LookupError(f"Unknown vendor {vendor_id}")
    nodes = set(nx.ego_graph(g, center, radius=depth).nodes)
    if len(nodes) > max_nodes:
        # Keep corporate neighbourhood first, then tenders.
        ranked = sorted(nodes, key=lambda n: (g.nodes[n]["type"] == "tender", n))
        nodes = set(ranked[:max_nodes]) | {center}
    view = _serialise(g, nodes)
    view["center"] = center
    return view


def relationship_paths(g: nx.MultiGraph, a: str, b: str, include_tenders: bool = False) -> list[dict]:
    """Explain how two vendors are connected: every intermediate node they share."""
    na, nb = _vendor_node(a), _vendor_node(b)
    paths = []
    for mid in sorted(set(g.neighbors(na)) & set(g.neighbors(nb))):
        mtype = g.nodes[mid]["type"]
        if mtype == "tender" and not include_tenders:
            continue
        edge_a = next(iter(g.get_edge_data(na, mid).values()))
        edge_b = next(iter(g.get_edge_data(nb, mid).values()))
        paths.append({
            "via": {"id": mid, **g.nodes[mid]},
            "edges": [edge_a["type"], edge_b["type"]],
            "evidence": [edge_a, edge_b],
        })
    return paths


def run_graph_stage(conn: sqlite3.Connection, tender_id: str) -> dict:
    g = build_graph(conn, tender_id)
    view = tender_view(g, tender_id)
    bidder_nodes = [n["id"] for n in view["nodes"] if n["type"] == "vendor" and n["is_bidder"]]
    corporate = nx.Graph()
    corporate.add_nodes_from(bidder_nodes)
    for a, b in combinations(bidder_nodes, 2):
        shared = [m for m in set(g.neighbors(a)) & set(g.neighbors(b)) if g.nodes[m]["type"] in ("director", "address", "contact")]
        if shared:
            corporate.add_edge(a, b, shared=shared)
    clusters = [sorted(c) for c in nx.connected_components(corporate) if len(c) > 1]
    summary = {
        "tender_id": tender_id,
        "full_graph": {"nodes": g.number_of_nodes(), "edges": g.number_of_edges()},
        "tender_view": view["stats"],
        "corporate_clusters": clusters,
        "degree_centrality": {
            n: round(c, 4) for n, c in nx.degree_centrality(nx.Graph(g)).items() if n in bidder_nodes
        },
    }
    put_artifact(conn, tender_id, "graph", summary, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return summary
