"""Stage 4: technical dependency graph between components.

Edge weight = engineering prior for the capability pair (documented below, editable) + evidence
found in the tender text. Every text-derived adjustment carries the quote and page it came from.

Strength bands
  strong   (>= 0.75)  keep in the same package (hard constraint for the optimiser)
  moderate (0.45-0.75) separable with an interface-management cost
  weak     (< 0.45)   separable
"""

from __future__ import annotations

import re
from itertools import combinations

import networkx as nx

from .taxonomy import lexicon_hits

STRONG, MODERATE = 0.75, 0.45

# (capability A, capability B): (prior weight, dependency type, rationale)
PRIORS: dict[frozenset, tuple[float, str, str]] = {
    frozenset(p): v for p, v in {
        ("civil_works", "structural_fabrication"): (0.55, "installation", "Structures sit on civil foundations; erection follows civil milestones."),
        ("civil_works", "mechanical_hvac_plumbing"): (0.45, "installation",
                                                         "Pipelines and pump houses need trenches, chambers and civil restoration."),
        ("civil_works", "electrical"): (0.35, "installation", "Cable trenches, substation plinths and earthing pits are civil scope."),
        ("civil_works", "signalling_control"): (0.40, "installation", "Signal foundations and cable routes depend on civil works."),
        ("civil_works", "instrumentation_sensors"): (0.25, "installation", "Meter/sensor chambers are civil items; devices are separable."),
        ("civil_works", "telecom_networks"): (0.30, "installation", "Ducts and trenching for fibre are shared with civil works."),
        ("electrical", "mechanical_hvac_plumbing"): (0.45, "interface", "Pumps, motors and HVAC need power supply, starters and controls."),
        ("electrical", "signalling_control"): (0.60, "safety", "Signalling power supply is part of the safety case."),
        ("electrical", "instrumentation_sensors"): (0.35, "interface", "Field devices need power and surge protection."),
        ("signalling_control", "ict_software"): (0.80, "safety", "Safety-critical control logic and its software are certified together."),
        ("signalling_control", "telecom_networks"): (0.60, "interface", "Signalling relies on the communication backbone."),
        ("instrumentation_sensors", "ict_software"): (0.55, "interface",
                                                       "Sensor data must reach the control/monitoring software (protocols, data model)."),
        ("instrumentation_sensors", "telecom_networks"): (0.45, "interface", "Telemetry needs the communication network."),
        ("ict_software", "telecom_networks"): (0.50, "interface", "Software runs over the network; performance is shared."),
        ("mechanical_hvac_plumbing", "instrumentation_sensors"): (0.40, "interface", "Flow/pressure instruments are fitted on mechanical systems."),
        ("structural_fabrication", "mechanical_hvac_plumbing"): (0.35, "installation", "Tanks, supports and pipe racks carry mechanical equipment."),
        ("electrical", "ict_software"): (0.30, "interface", "Control panels and software share I/O definitions."),
        ("electrical", "industrial_machinery"): (0.40, "interface", "Process machines need power supply, starters and controls."),
        ("civil_works", "industrial_machinery"): (0.30, "installation", "Machine foundations and plant sheds are civil scope."),
        ("industrial_machinery", "mechanical_hvac_plumbing"): (0.35, "interface", "Process lines share utilities (air, water, steam)."),
        ("industrial_machinery", "instrumentation_sensors"): (0.30, "interface", "Process instruments are fitted on the machines."),
    }.items()
}
DEFAULT_PRIOR = (0.15, "schedule", "Shared site and programme only.")
O_AND_M = "operation_maintenance"
DESIGN = "consultancy_design"

CUES = {
    "safety": re.compile(r"\b(safety|sil[- ]?\d|fail[- ]safe|interlock|vital|hazard|rdso)\b", re.I),
    "interface": re.compile(r"\b(interface|integrat\w*|compatib\w*|protocol|modbus|rs[- ]?485|api|scada|communicat\w*)\b", re.I),
    "schedule": re.compile(r"\b(prior to|before (?:the )?commencement|after (?:the )?completion|upon completion|"
                           r"in sequence|simultaneous\w*|shall be completed before)\b", re.I),
    "installation": re.compile(r"\b(mounted|embedded|installed (?:in|on)|housed in|foundation for|chamber for)\b", re.I),
}
OPEN_STANDARD = re.compile(r"\b(open (?:protocol|standard|api)|mqtt|opc[- ]?ua|modbus|iec 61850|iec 60870|"
                           r"rest(?:ful)? api|bacnet|dlms)\b", re.I)
SINGLE_RESPONSIBILITY = re.compile(r"\b(single point (?:of )?responsibility|sole responsibility|turnkey|\bepc\b|"
                                   r"entire system|end[- ]to[- ]end|complete system)\b", re.I)
TEXT_BOOST, TEXT_BOOST_CAP, OPEN_STANDARD_RELIEF = 0.15, 0.30, 0.10


def _band(w: float) -> str:
    return "strong" if w >= STRONG else "moderate" if w >= MODERATE else "weak"


def _caps_in(text: str, item_caps: set[str]) -> set[str]:
    return set(lexicon_hits(text)) | item_caps


def build_dependency_graph(components: list[dict], pages: list[tuple[str, int, str]]) -> dict:
    by_cap = {c["capability"]: c for c in components}
    present = set(by_cap)
    evidence: dict[frozenset, list[dict]] = {}
    relief: dict[frozenset, list[dict]] = {}
    tender_flags = []

    # Evidence: two present capabilities named together with a coupling cue, either in one sentence of
    # the documents or inside one scope item (whose own capability counts as named).
    units = [(doc, page, sent, set()) for doc, page, text in pages for sent in re.split(r"(?<=[.:])\s+|\n", text)]
    units += [(i["document_id"], i.get("page"), i["text"], {c["capability"]}) for c in components for i in c.get("items", [])]
    seen_units = set()
    for doc, page, sent, own in units:
        if len(sent) < 25 or (sent, frozenset(own)) in seen_units:
            continue
        seen_units.add((sent, frozenset(own)))
        caps = _caps_in(sent, own) & present
        if not own and SINGLE_RESPONSIBILITY.search(sent):
            tender_flags.append({"type": "single_responsibility", "document_id": doc, "page": page, "quote": sent.strip()[:240]})
        if len(caps) < 2:
            continue
        for a, b in combinations(sorted(caps), 2):
            key = frozenset((a, b))
            for cue_type, rx in CUES.items():
                if rx.search(sent):
                    evidence.setdefault(key, []).append({"type": cue_type, "document_id": doc, "page": page,
                                                         "quote": sent.strip()[:240]})
                    break
            if OPEN_STANDARD.search(sent):
                relief.setdefault(key, []).append({"document_id": doc, "page": page, "quote": sent.strip()[:240]})

    g = nx.Graph()
    for c in components:
        g.add_node(c["component_id"], capability=c["capability"], label=c["label"], value_inr_cr=c["value_inr_cr"])
    edges = []
    for a, b in combinations(components, 2):
        key = frozenset((a["capability"], b["capability"]))
        if O_AND_M in key:
            prior = (0.30, "schedule", "O&M follows the asset it maintains; separable with clear handover and defect-liability terms.")
        elif DESIGN in key:
            prior = (0.10, "independence", "Design / supervision is normally procured separately from works so the supervising "
                                           "engineer is independent of the contractor.")
        else:
            prior = PRIORS.get(key, DEFAULT_PRIOR)
        ev = evidence.get(key, [])
        boost = min(TEXT_BOOST_CAP, TEXT_BOOST * len({e["type"] for e in ev}))
        rel = relief.get(key, [])
        w = round(max(0.0, min(1.0, prior[0] + boost - (OPEN_STANDARD_RELIEF if rel else 0.0))), 3)
        types = sorted({prior[1]} | {e["type"] for e in ev})
        edge = {"source": a["component_id"], "target": b["component_id"], "capabilities": sorted(key),
                "weight": w, "strength": _band(w), "types": types, "prior": prior[0], "prior_rationale": prior[2],
                "text_evidence": ev[:4], "open_standard_evidence": rel[:2]}
        edges.append(edge)
        g.add_edge(a["component_id"], b["component_id"], weight=w, strength=edge["strength"])
    strong_groups = [sorted(cc) for cc in nx.connected_components(
        nx.Graph([(e["source"], e["target"]) for e in edges if e["strength"] == "strong"]))]
    return {"nodes": [{"id": n, **d} for n, d in g.nodes(data=True)], "edges": edges,
            "strong_groups": strong_groups, "tender_flags": tender_flags[:6],
            "thresholds": {"strong": STRONG, "moderate": MODERATE}}
