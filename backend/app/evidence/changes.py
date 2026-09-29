"""Version change analysis and the explanation layer.

Layers, in order of authority:

1. SHA-256 (``versions``)            - objective: "the hashes differ".
2. Field / text comparison (here)    - objective: "these values changed", with page + excerpt.
3. Rulebook re-check (here)          - objective: "this field is eligibility rule R-03; PASS before, PASS after".
4. Explanation (Claude or template)  - explains and suggests what to verify. It receives layers 1-3 as
                                       fixed facts and can never change them.
5. Auditor                           - decides (``versions.review_version``).

Values are only reported when a pattern extracted them from the document text; nothing is
inferred or filled in.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import date

from pydantic import BaseModel, Field

from ..compliance.engine import FAIL, evaluate_rule
from ..config import get_settings
from ..db import fetch_one
from ..ingestion.facts import DIRECTOR_LINE, extract_facts_from_pages, load_facts
from ..nlp.extract import load_rules
from ..nlp.llm_extractor import llm_available
from ..nlp.rulebook import METRICS
from . import versions

log = logging.getLogger(__name__)

# Identity / certificate fields not covered by the rulebook vocabulary: (regex over one line, label, category).
EXTRA_FIELDS: dict[str, tuple[str, str, str]] = {
    "company_name": (r"^(?:Compliance Documents|Technical Proposal) - (.+)$", "Company name", "identity"),
    "gstin": (r"GSTIN\s*([0-9A-Z]{15})", "GSTIN", "identity"),
    "pan_number": (r"PAN:\s*([A-Z]{5}\d{4}[A-Z])", "PAN", "identity"),
    "registered_address": (r"Registered office:\s*(.+?)\.?$", "Registered address", "identity"),
    "certificate_number": (r"Certificate No\.\s*([\w/.-]+)", "ISO 9001 certificate number", "certificate"),
    "issuer": (r"Certified by:\s*(.+)$", "Certifying authority", "certificate"),
    "udyam_number": (r"Udyam Registration:\s*(UDYAM-[\w-]+)", "Udyam registration number", "certificate"),
    "emd_reference": (r"e-payment reference\s*([\w-]+)", "EMD payment reference", "declared_value"),
}
VALIDITY_METRICS = {"iso9001_valid_until", "iso27001_valid_until"}
BANNED_TERMS = re.compile(r"\b(fraud\w*|fake|forged|forgery|guilty|legitimate|illegitimate|genuine|authentic|"
                          r"invalid|valid document|tamper\w*)\b", re.IGNORECASE)


def _extract(pages: list[tuple[int, str]]) -> dict[str, dict]:
    fields = extract_facts_from_pages(pages)
    for page, text in pages:
        for line in text.splitlines():
            for name, (pattern, _, _) in EXTRA_FIELDS.items():
                if name in fields:
                    continue
                m = re.search(pattern, line.strip())
                if m:
                    fields[name] = {"value": m.group(1).strip(), "page": page, "excerpt": line.strip()}
    directors = [(p, m) for p, text in pages for m in DIRECTOR_LINE.finditer(text)]
    if directors:
        fields["directors"] = {"value": "; ".join(sorted(f"{m.group(1)} (DIN {m.group(2)})" for _, m in directors)),
                               "page": directors[0][0], "excerpt": "Director list"}
    return fields


def _field_label(name: str) -> str:
    if name in METRICS:
        return METRICS[name]["label"]
    if name == "directors":
        return "Declared directors"
    return EXTRA_FIELDS.get(name, (None, name.replace("_", " ").capitalize(), None))[1]


def _category(name: str, rule: dict | None) -> str:
    if name in VALIDITY_METRICS:
        return "validity"
    if rule is not None:
        return "eligibility"
    if name == "directors":
        return "identity"
    if name in EXTRA_FIELDS:
        return EXTRA_FIELDS[name][2]
    return "declared_value"


def _display(name: str, value) -> str:
    if value is None:
        return "—"
    unit = METRICS.get(name, {}).get("unit", "")
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)) and unit == "crore":
        return f"₹{value:.2f} crore"
    if isinstance(value, (int, float)) and unit == "lakh":
        return f"₹{value:g} lakh"
    if isinstance(value, (int, float)):
        return f"{value:g} {unit}".strip()
    return str(value)


def _months_between(old: str, new: str) -> int | None:
    try:
        a, b = date.fromisoformat(old), date.fromisoformat(new)
    except (TypeError, ValueError):
        return None
    return (b.year - a.year) * 12 + (b.month - a.month)


def _rule_check(rule: dict, name: str, old, new, facts: dict, deadline: str | None) -> dict:
    def run(value) -> dict:
        trial = {**facts, name: {"value": value}} if value is not None else {k: v for k, v in facts.items() if k != name}
        return evaluate_rule(rule, trial, deadline)

    before, after = run(old), run(new)
    return {"rule_id": rule["rule_id"], "requirement": rule.get("requirement"), "expected": before["expected"],
            "mandatory": rule["mandatory"], "before": before["result"], "after": after["result"],
            "after_reason": after["reason"], "outcome_changed": before["result"] != after["result"]}


def _assess(change: dict) -> None:
    """Deterministic triage flags + one factual note per change."""
    category, check = change["category"], change.get("rule_check")
    months = _months_between(change["old_value"], change["new_value"]) if category == "validity" else None
    change["potentially_routine"] = bool(months and months > 0 and change["change_type"] == "modified")
    change["affects_eligibility"] = check is not None
    change["requires_verification"] = (category in ("identity", "certificate") or check is not None
                                       or change["change_type"] == "removed")
    if check and check["after"] == FAIL:
        note = (f"Deterministic rule check: requirement {check['rule_id']} is not met with the new value "
                f"({check['after_reason']})")
    elif check and check["outcome_changed"]:
        note = f"Rule {check['rule_id']} outcome changes from {check['before']} to {check['after']}."
    elif category == "validity" and months is not None:
        note = (f"Validity {'extended' if months > 0 else 'shortened'} by {abs(months)} month(s)"
                + (" - consistent with a certificate renewal; confirm with the issuing body." if months > 0 else "."))
    elif check:
        note = (f"Eligibility value for rule {check['rule_id']}: {check['before']} before, {check['after']} after. "
                "Verify against the source record.")
    elif category in ("identity", "certificate"):
        note = "Identity / certificate reference changed - verify against the issuing registry."
    else:
        note = "Declared value changed."
    change["note"] = note
    if check and check["after"] == FAIL:
        change["impact"] = "rule_failed"
    elif change["potentially_routine"] and not (check and check["outcome_changed"]):
        change["impact"] = "routine"
    elif check:
        change["impact"] = "eligibility"
    else:
        change["impact"] = "verify" if change["requires_verification"] else "informational"


def compare_versions(conn: sqlite3.Connection, document_id: str, from_version: int | None = None,
                     to_version: int | None = None) -> dict:
    listing = versions.list_versions(conn, document_id)
    to_row = versions.get_version_row(conn, document_id, to_version or listing["latest_version"])
    if from_version is None:
        parent = versions.version_by_id(conn, to_row["parent_version_id"]) if to_row["parent_version_id"] else None
        from_version = parent["version"] if parent else to_row["version"]
    from_row = versions.get_version_row(conn, document_id, from_version)

    old_fields = _extract(versions.version_pages(conn, from_row["version_id"]))
    new_fields = _extract(versions.version_pages(conn, to_row["version_id"]))
    tender = fetch_one(conn, "SELECT bid_deadline FROM tenders WHERE tender_id = ?", (to_row["tender_id"],)) or {}
    rules = {r["metric"]: r for r in load_rules(conn, to_row["tender_id"])}
    facts = load_facts(conn, to_row["tender_id"]).get(listing["vendor_id"] or "", {})

    changes, unchanged = [], []
    for name in sorted(set(old_fields) | set(new_fields)):
        old, new = old_fields.get(name), new_fields.get(name)
        old_v, new_v = (old or {}).get("value"), (new or {}).get("value")
        if old_v == new_v:
            if old is not None:
                unchanged.append({"field": name, "label": _field_label(name), "value": _display(name, old_v)})
            continue
        rule = rules.get(name) if name in METRICS else None
        change = {
            "field": name, "label": _field_label(name),
            "old_value": old_v, "new_value": new_v,
            "old_display": _display(name, old_v), "new_display": _display(name, new_v),
            "change_type": "added" if old is None else "removed" if new is None else "modified",
            "old_source": {"page": old["page"], "excerpt": old["excerpt"]} if old else None,
            "new_source": {"page": new["page"], "excerpt": new["excerpt"]} if new else None,
            "category": _category(name, rule),
            "rule_check": _rule_check(rule, name, old_v, new_v, facts, tender.get("bid_deadline")) if rule else None,
        }
        _assess(change)
        changes.append(change)

    # Free-text lines that changed but are not explained by a structured field.
    covered = {c[k]["excerpt"] for c in changes for k in ("old_source", "new_source") if c.get(k)}
    old_lines = {(p, line) for p, text in versions.version_pages(conn, from_row["version_id"]) for line in text.splitlines()}
    new_lines = {(p, line) for p, text in versions.version_pages(conn, to_row["version_id"]) for line in text.splitlines()}
    old_text, new_text = {line for _, line in old_lines}, {line for _, line in new_lines}
    text_changes = (
        [{"page": p, "change_type": "removed", "text": line} for p, line in sorted(old_lines)
         if line not in new_text and line not in covered]
        + [{"page": p, "change_type": "added", "text": line} for p, line in sorted(new_lines)
           if line not in old_text and line not in covered]
    )[:30]

    return {
        "document_id": document_id, "tender_id": to_row["tender_id"], "vendor_id": listing["vendor_id"],
        "filename": listing["filename"],
        "from_version": versions.label(from_row["version"]), "to_version": versions.label(to_row["version"]),
        "from_version_id": from_row["version_id"], "to_version_id": to_row["version_id"],
        "from_status": from_row["status"], "to_status": to_row["status"],
        "hashes": {"from": from_row["sha256"], "to": to_row["sha256"], "differ": from_row["sha256"] != to_row["sha256"]},
        "changes": changes,
        "unchanged": unchanged,
        "text_changes": text_changes,
        "counts": {
            "changes": len(changes),
            "affects_eligibility": sum(c["affects_eligibility"] for c in changes),
            "requires_verification": sum(c["requires_verification"] for c in changes),
            "potentially_routine": sum(c["potentially_routine"] for c in changes),
            "rule_failed": sum(c["impact"] == "rule_failed" for c in changes),
        },
        "method": "deterministic",
    }


# --- Explanation ----------------------------------------------------------------------------

class VersionExplanation(BaseModel):
    summary: str = Field(description="2-4 sentences: what changed and what the auditor should do next")
    what_changed: list[str]
    potentially_routine: list[str] = Field(description="Changes consistent with normal document maintenance")
    affects_eligibility: list[str] = Field(description="Changes touching a tender eligibility rule")
    requires_verification: list[str] = Field(description="Changes that need manual verification")
    auditor_checks: list[str] = Field(description="Concrete checks the auditor should perform")


EXPLAIN_SYSTEM = """You help a public-procurement auditor review a new version of a bidder document. \
You receive facts already established by deterministic systems: whether SHA-256 hashes differ, which \
fields changed (with the exact extracted values), and how each change evaluates against the tender's \
eligibility rules. Treat those facts as fixed. Do not recompute, doubt or contradict them, and do not \
add values that are not in the input.

Your only job is to explain and triage: what changed, which changes look like normal document \
maintenance, which affect tender eligibility, which require manual verification, and what exactly the \
auditor should check (for example, which issuing authority or financial record to confirm against).

Never state or imply a verdict about the document or the bidder. Do not use the words fraud, fake, \
forged, guilty, legitimate, genuine, authentic, tampered, valid or invalid. Say "consistent with" or \
"should be verified" instead. The auditor makes the final decision. Keep each list item to one sentence."""


def _lc(text: str) -> str:
    """Lower-case a label's first letter for mid-sentence use, keeping acronyms (ISO, GSTIN, PAN)."""
    return text[0].lower() + text[1:] if len(text) > 1 and text[1].islower() else text


def _template(comparison: dict) -> dict:
    changes = comparison["changes"]
    frm, to = comparison["from_version"], comparison["to_version"]
    what = [f"{c['label']}: {c['old_display']} → {c['new_display']}" if c["change_type"] == "modified"
            else f"{c['label']} {c['change_type']}: {c['new_display'] if c['change_type'] == 'added' else c['old_display']}"
            for c in changes]
    what += [f"Text {t['change_type']} on page {t['page']}: \"{t['text']}\"" for t in comparison["text_changes"][:5]]
    routine = [f"{c['label']}: {c['note']}" for c in changes if c["potentially_routine"]]
    eligibility = []
    for c in changes:
        chk = c.get("rule_check")
        if chk:
            eligibility.append(f"{c['label']} is tender requirement {chk['rule_id']} ({chk['expected']}); "
                               f"rule result {chk['before']} with {frm}, {chk['after']} with {to}.")
    verify = [f"{c['label']} ({c['old_display']} → {c['new_display']})" for c in changes if c["requires_verification"]]
    checks = []
    for c in changes:
        if c["category"] == "validity":
            cert = next((u["value"] for u in comparison["unchanged"] if u["field"] == "certificate_number"), None)
            checks.append(f"Confirm the {_lc(c['label'])} ({c['new_display']}) with the issuing certification body"
                          + (f" using certificate number {cert}." if cert else "."))
        elif c["affects_eligibility"] and METRICS.get(c["field"], {}).get("category") == "Financial":
            checks.append(f"Verify the revised {_lc(c['label'])} against the audited financial statements "
                          "or the Chartered Accountant's certificate.")
        elif c["affects_eligibility"]:
            checks.append(f"Verify the revised {_lc(c['label'])} against its supporting record.")
        elif c["category"] in ("identity", "certificate"):
            checks.append(f"Confirm the change to {_lc(c['label'])} against the official registry (MCA / GST / "
                          "issuing body).")
    if not changes and not comparison["text_changes"]:
        checks.append("No extractable content differences; compare the two files manually.")

    kept = [u["label"] for u in comparison["unchanged"] if u["field"] in ("company_name", "certificate_number", "issuer")]
    sentences = [f"Version {to[1:]} differs from Version {frm[1:]} in {len(changes)} extracted field(s)"
                 + (f" and {len(comparison['text_changes'])} other text line(s)." if comparison["text_changes"] else ".")]
    if kept:
        names = kept[0] if len(kept) == 1 else ", ".join([kept[0], *map(_lc, kept[1:-1])]) + " and " + _lc(kept[-1])
        sentences.append(f"{names} remain{'s' if len(kept) == 1 else ''} unchanged.")
    if routine:
        sentences.append("Extended validity dates are consistent with a possible renewal, but the issuing "
                         "authority should be confirmed before relying on the new document.")
    material = [c for c in changes if c["impact"] in ("eligibility", "rule_failed")]
    if material:
        names = ", ".join(f"{_lc(c['label'])} ({c['old_display']} → {c['new_display']}, rule {c['rule_check']['rule_id']})"
                          for c in material)
        sentences.append(f"The change to {names} affects a tender eligibility requirement and should be manually "
                         "verified against the issuing record.")
    failed = [c for c in changes if c["impact"] == "rule_failed"]
    if failed:
        sentences.append(f"The deterministic rule check reports {len(failed)} requirement(s) not met with the new values.")
    sentences.append("The auditor decides whether to accept the new version.")
    return {"summary": " ".join(sentences), "what_changed": what, "potentially_routine": routine,
            "affects_eligibility": eligibility, "requires_verification": verify, "auditor_checks": checks}


def explain_with_llm(comparison: dict, integrity: dict) -> tuple[dict, str]:
    """Return (explanation, model). Raises on API failure or refusal - the caller falls back."""
    import anthropic

    settings = get_settings()
    facts = {
        "integrity_facts": integrity,
        "document": {k: comparison[k] for k in ("filename", "from_version", "to_version")},
        "changed_fields": [{k: c[k] for k in ("label", "change_type", "old_display", "new_display", "category",
                                              "potentially_routine", "affects_eligibility", "requires_verification",
                                              "rule_check", "note")} for c in comparison["changes"]],
        "unchanged_fields": comparison["unchanged"],
        "other_text_changes": comparison["text_changes"][:15],
    }
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=settings.llm_model,
        max_tokens=16000,
        system=EXPLAIN_SYSTEM,
        messages=[{"role": "user", "content": "Explain this document version change for the auditor.\n\n"
                                              + json.dumps(facts, indent=2, ensure_ascii=False, default=str)}],
        output_format=VersionExplanation,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("LLM declined the explanation request")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("LLM output was truncated (max_tokens)")
    if response.parsed_output is None:
        raise RuntimeError("LLM returned no structured output")
    return response.parsed_output.model_dump(), response.model


def _has_verdict_language(explanation: dict) -> bool:
    texts = [explanation["summary"], *[s for key in ("what_changed", "potentially_routine", "affects_eligibility",
                                                    "requires_verification", "auditor_checks")
                                       for s in explanation[key]]]
    return any(BANNED_TERMS.search(t) for t in texts)


def explain_changes(comparison: dict, integrity: dict, method: str | None = None) -> dict:
    """Explain a comparison. ``method``: auto (Claude when configured), llm, or template.

    The integrity facts and rule checks are returned unchanged next to the explanation, and the
    explanation carries no status field: it cannot mark a mismatch as verified or accept a version.
    """
    method = (method or "auto").lower()
    warnings: list[str] = []
    explanation, used, model = None, "template", None
    if method in ("auto", "llm") and llm_available():
        try:
            candidate, model = explain_with_llm(comparison, integrity)
            if _has_verdict_language(candidate):
                warnings.append("LLM explanation used verdict language and was replaced by the rule-based explanation.")
                model = None
            else:
                explanation, used = candidate, "llm"
        except Exception as exc:  # network, auth, refusal, schema - never block the auditor
            log.warning("LLM explanation failed, using template: %s", exc)
            warnings.append(f"LLM explanation unavailable ({type(exc).__name__}); showing the rule-based explanation.")
            model = None
    elif method == "llm":
        warnings.append("No Anthropic credentials configured; showing the rule-based explanation.")
    if explanation is None:
        explanation = _template(comparison)
    return {
        "method": used, "model": model, **explanation,
        "integrity_facts": integrity,
        "counts": comparison["counts"],
        "warnings": warnings,
        "guardrail": "Explanations are advisory. SHA-256 results and rule checks are computed deterministically and "
                     "cannot be changed by the explanation; only an auditor can accept a new version.",
    }


def integrity_facts(conn: sqlite3.Connection, comparison: dict) -> dict:
    doc = comparison["document_id"]
    old = versions.verify_version(conn, doc, int(comparison["from_version"][1:]))
    new = versions.verify_version(conn, doc, int(comparison["to_version"][1:]))
    return {
        "hashes_differ": comparison["hashes"]["differ"],
        "from_version": {"label": old["label"], "status": old["status"], "hash_matches_record": old["match"]},
        "to_version": {"label": new["label"], "status": new["status"], "hash_matches_record": new["match"],
                       "review_status": new["version_status"]},
        "historical_version_unchanged": old["match"],
    }

