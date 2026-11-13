"""Capability taxonomy for procurement restructuring (SDG 9.3 primary objective).

Each capability is defined by Common Procurement Vocabulary (CPV 2008) code prefixes, so any
real dataset that carries CPV codes (Prozorro, EU TED, many OCDS publishers) maps onto it with
no manual labelling, and the CPV vocabulary itself (9,454 official descriptions) is the training
set for the text classifier in ``classifier.py``.

The keyword lexicon is a small, curated layer for Indian tender phrasing (CPWD / CPPP BOQ style)
that the CPV vocabulary does not use ("providing and laying", "SITC", "RCC"). It is combined with
the model, never used on its own as a verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Capability:
    key: str
    label: str
    cpv_prefixes: tuple[str, ...]
    keywords: tuple[str, ...] = field(default_factory=tuple)
    # Typical role in an infrastructure contract; "works" packages need site presence.
    nature: str = "goods"  # works | goods | services


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        "civil_works", "Civil & building construction",
        ("45", "451", "452", "4541", "4542", "4543", "4544", "4545", "441", "448", "449"),
        ("excavation", "earthwork", "rcc", "reinforced cement concrete", "pcc", "brickwork", "masonry", "plastering",
         "foundation", "pile", "road work", "bituminous", "culvert", "drain", "building", "civil work", "flooring",
         "shuttering", "formwork", "road marking", "pedestrian crossing", "junction geometry", "footpath",
         "embankment", "bridge", "retaining wall", "pavement", "kerb", "boundary wall",
         "providing and laying", "cement concrete", "sub-base", "backfilling",
         "viaduct", "elevated station", "station building", "flyover", "tunnel", "metro corridor", "protection work",
         "road", "metalling", "tarring", "pmgsy", "classroom", "playground", "play ground", "channelization", "wall"),
        "works"),
    Capability(
        "electrical", "Electrical systems & power",
        ("4531", "31", "0931", "6531", "4432"),
        ("electrical", "cable", "switchgear", "transformer", "panel", "lt panel", "ht panel", "earthing", "lighting",
         "luminaire", "substation", "dg set", "diesel generator", "ups", "busbar", "wiring", "conduit", "mcb", "acb",
         "feeder", "power supply", "solar", "inverter", "kv", "sub-station", "transmission line", "gis",
         "switchyard", "distribution line", "electrification"),
        "works"),
    Capability(
        "signalling_control", "Signalling, traffic & safety control",
        ("34632", "3499", "3492", "45234115", "45316", "45233294"),
        ("signalling", "signaling", "interlocking", "track circuit", "axle counter", "traffic signal", "atcs",
         "level crossing", "adaptive traffic", "point machine", "train protection", "kavach", "sil-4", "sil 4", "fail-safe",
         "traffic control", "variable message sign", "vms"),
        "works"),
    Capability(
        "instrumentation_sensors", "Instrumentation, sensors & metering",
        ("38",),
        ("sensor", "meter", "transmitter", "flow meter", "flowmeter", "water meter", "smart meter", "pressure gauge",
         "level sensor", "temperature sensor", "instrumentation", "calibration", "analyser", "analyzer",
         "data logger", "iot", "telemetry", "rtu", "plc", "metering", "ultrasonic"),
        "goods"),
    Capability(
        "ict_software", "Software, ICT & control systems",
        ("48", "72", "30"),
        ("software", "scada", "application", "database", "server", "dashboard", "integration platform", "erp",
         "web portal", "mobile app", "cloud", "network management", "command and control", "data centre", "integration with",
         "command centre", "command center", "video wall", "analytics", "e-challan",
         "data center", "cybersecurity", "it hardware", "computer", "workstation", "license", "licence"),
        "services"),
    Capability(
        "telecom_networks", "Telecom & communication networks",
        ("32", "6420", "45232332", "45314"),
        ("optical fibre", "optical fiber", "ofc", "telecom", "radio", "communication", "network switch", "router",
         "wireless", "lora", "gsm", "cctv", "camera", "public address", "pa system", "lan", "wan", "surveillance"),
        "goods"),
    Capability(
        "mechanical_hvac_plumbing", "Mechanical, HVAC, pumps & plumbing",
        ("4533", "4535", "42", "39715", "4416", "4413", "4462", "4448", "45232"),
        ("hvac", "air conditioning", "chiller", "ventilation", "pump", "pumping", "motor", "valve", "plumbing",
         "pipe", "pipeline", "di pipe", "hdpe", "upvc", "sluice", "fire fighting", "sprinkler", "lift", "elevator",
         "compressor", "crane", "sewer", "water supply", "sanitary"),
        "works"),
    Capability(
        # CPV 422 food/beverage machinery, 423 furnaces & ovens, 426 machine tools, 427 textile, 428 paper,
        # 4291-4294 / 4297 / 4299 process, packing and weighing machinery. Real World Bank India goods
        # notices (agro-processing plants) were being forced into mechanical / vehicles / medical without it.
        "industrial_machinery", "Industrial & process machinery",
        ("422", "423", "426", "427", "428", "4291", "4292", "4293", "4294", "4297", "4299"),
        ("processing line", "processing plant", "processing machinery", "mill", "milling", "chakki", "extruder",
         "extrusion", "dryer", "oven", "packing machine", "packaging machine", "sealing machine", "weighing scale",
         "weighing balance", "conveyor", "grader", "destoner", "dehuller", "roaster", "flaker", "pulverizer",
         "machine tool", "cnc", "lathe", "boiler", "furnace", "food processing", "cold storage plant"),
        "goods"),
    Capability(
        "structural_fabrication", "Structural steel & specialised fabrication",
        ("442", "4433", "4443", "4445", "4447", "4461", "45223", "45262"),
        ("structural steel", "fabrication", "steel structure", "truss", "girder", "gantry", "shed", "roofing sheet",
         "welding", "galvanised", "galvanized", "ms structure", "tank fabrication", "railing", "grating"),
        "goods"),
    Capability(
        "consultancy_design", "Design, engineering & supervision services",
        ("71", "79", "73"),
        ("design", "consultancy", "detailed project report", "dpr", "survey", "supervision", "project management",
         "third party inspection", "quality audit", "feasibility", "geotechnical investigation"),
        "services"),
    Capability(
        "operation_maintenance", "Operation & maintenance services",
        ("50", "90", "6512", "6511"),
        ("operation and maintenance", "o&m", "comprehensive maintenance", "amc", "annual maintenance", "camc",
         "housekeeping", "cleaning", "repair", "upkeep", "warranty support"),
        "services"),
    Capability(
        "vehicles_equipment", "Vehicles & heavy equipment",
        ("34", "43", "16"),
        ("vehicle", "truck", "bus", "tractor", "excavator", "jcb", "loader", "roller", "dumper", "ambulance",
         "tanker", "water tanker", "sucker", "jetting machine", "utility vehicle", "tipper", "compactor"),
        "goods"),
    Capability(
        "medical_lab", "Medical & laboratory equipment",
        ("33",),
        ("medical", "hospital equipment", "laboratory", "diagnostic", "surgical", "x-ray", "ventilator"),
        "goods"),
)

OTHER = "other_goods_services"
CAPABILITY_KEYS: tuple[str, ...] = tuple(c.key for c in CAPABILITIES) + (OTHER,)
BY_KEY = {c.key: c for c in CAPABILITIES}
LABELS = {**{c.key: c.label for c in CAPABILITIES}, OTHER: "Other goods & services"}

# Ordered longest-prefix-first so e.g. 3463 (railway traffic control) beats 34 (vehicles).
_PREFIX_INDEX: list[tuple[str, str]] = sorted(
    ((p, c.key) for c in CAPABILITIES for p in c.cpv_prefixes), key=lambda pk: -len(pk[0])
)
_KEYWORD_PATTERNS = {
    c.key: [re.compile(r"(?<![a-z0-9])" + re.escape(k) + r"(?:s|es)?(?![a-z0-9])") for k in c.keywords] for c in CAPABILITIES
}


def cpv_digits(code: str | None) -> str:
    return re.sub(r"\D", "", (code or "").split("-")[0])


def capability_for_cpv(code: str | None) -> str:
    """Map a CPV code (``45232151-5``, ``45232151`` or just a division ``45``) to a capability key."""
    digits = cpv_digits(code)
    if not digits:
        return OTHER
    for prefix, key in _PREFIX_INDEX:
        if digits.startswith(prefix):
            return key
    return OTHER


def lexicon_hits(text: str) -> dict[str, list[str]]:
    """Return {capability: [matched keywords]} for a piece of tender text."""
    lowered = text.lower()
    hits: dict[str, list[str]] = {}
    for key, patterns in _KEYWORD_PATTERNS.items():
        found = [p.pattern for p in patterns if p.search(lowered)]
        if found:
            hits[key] = [_strip_pattern(f) for f in found]
    return hits


def _strip_pattern(pattern: str) -> str:
    inner = pattern.removeprefix(r"(?<![a-z0-9])").removesuffix(r"(?:s|es)?(?![a-z0-9])")
    return re.sub(r"\\(.)", r"\1", inner)


def describe() -> list[dict]:
    return [{"key": c.key, "label": c.label, "nature": c.nature, "cpv_prefixes": list(c.cpv_prefixes)}
            for c in CAPABILITIES] + [{"key": OTHER, "label": LABELS[OTHER], "nature": "goods", "cpv_prefixes": []}]
