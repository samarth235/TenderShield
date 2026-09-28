import type { FindingLevel, ResultStatus, VendorRef } from "../api/types";

export const fmtCr = (v: number | null | undefined) => (v == null ? "—" : `₹${v.toFixed(2)} Cr`);

export const fmtPct = (v: number | null | undefined, digits = 1) => (v == null ? "—" : `${(v * 100).toFixed(digits)}%`);

export const fmtMs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`);

export const shortHash = (h: string | null | undefined, n = 6) =>
  h ? `${h.slice(0, n).toUpperCase()}…${h.slice(-n).toUpperCase()}` : "—";

export const fmtDateTime = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
};

export const vendorLabel = (v: Pick<VendorRef, "alias" | "name" | "vendor_id"> | undefined) =>
  v ? v.alias ?? v.name : "—";

export const vendorLetter = (v: Pick<VendorRef, "alias" | "name"> | undefined) => {
  if (!v) return "?";
  if (v.alias) return v.alias.split(" ").pop()!.slice(0, 1);
  return v.name.slice(0, 1);
};

export type Tone = "high" | "medium" | "low" | "pass" | "fail" | "unknown" | "na" | "accent" | "brand" | "outline";

export const levelTone = (level: FindingLevel | string): Tone =>
  (
    ({
      HIGH: "high",
      MEDIUM: "medium",
      LOW: "low",
      NONE: "na",
      FAIL: "fail",
      INSUFFICIENT_DATA: "unknown",
    }) as Record<string, Tone>
  )[level] ?? "outline";

export const resultTone = (r: ResultStatus | string): Tone =>
  (({ PASS: "pass", FAIL: "fail", UNKNOWN: "unknown", NOT_APPLICABLE: "na" }) as Record<string, Tone>)[r] ?? "outline";

export const statusTone = (s: string): Tone =>
  (
    ({
      QUALIFIED: "pass",
      NOT_QUALIFIED: "fail",
      INCOMPLETE_EVIDENCE: "unknown",
      OPEN: "outline",
      FURTHER_REVIEW: "medium",
      VERIFIED: "high",
      DISMISSED: "na",
    }) as Record<string, Tone>
  )[s] ?? "outline";

export const humanize = (s: string) =>
  s
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/^\w/, (c) => c.toUpperCase());

export const levelColor = (level: string) =>
  (
    ({
      HIGH: "var(--high)",
      MEDIUM: "var(--medium)",
      LOW: "var(--low)",
      NONE: "var(--na)",
      FAIL: "var(--fail)",
      INSUFFICIENT_DATA: "var(--unknown)",
    }) as Record<string, string>
  )[level] ?? "var(--ink-3)";

export const FAMILY_LABEL: Record<string, string> = {
  corporate: "Corporate",
  behavioural: "Behavioural",
  document: "Document",
  model: "ML model",
  compliance: "Compliance",
  data_quality: "Data quality",
};

export const CATEGORY_LABEL: Record<string, string> = {
  INVESTIGATION_SIGNAL: "Investigation signal",
  COMPLIANCE: "Compliance finding",
  DATA_QUALITY: "Data-quality warning",
};

export const STAGE_LABEL: Record<string, string> = {
  extract_rules: "AI rule extraction",
  ingest_evidence: "Evidence ingestion",
  compliance: "Compliance engine",
  entity_resolution: "Entity resolution",
  document_similarity: "Document similarity",
  relationship_graph: "Relationship graph",
  behaviour_analysis: "Behaviour + ML",
  reasoning: "Evidence reasoning",
};

export const prettyTitle = (t: string) => t.replace(/\s<->\s/g, " ↔ ");
