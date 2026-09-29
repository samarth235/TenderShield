// Response shapes of the TenderShield backend (see docs/backend-api.md).

export type ResultStatus = "PASS" | "FAIL" | "UNKNOWN" | "NOT_APPLICABLE";
export type VendorStatus = "QUALIFIED" | "NOT_QUALIFIED" | "INCOMPLETE_EVIDENCE";
export type SignalLevel = "HIGH" | "MEDIUM" | "LOW" | "NONE";
export type FindingLevel = SignalLevel | "FAIL" | "INSUFFICIENT_DATA";
export type FindingCategory = "INVESTIGATION_SIGNAL" | "COMPLIANCE" | "DATA_QUALITY";
export type FindingStatus = "OPEN" | "VERIFIED" | "DISMISSED" | "FURTHER_REVIEW";
export type Decision = Exclude<FindingStatus, "OPEN">;

export interface Health {
  status: string;
  extractor: string;
  llm_available: boolean;
  llm_model: string;
  embedding_backend: string;
}

export interface StageReport {
  stage: string;
  duration_ms: number;
  summary: Record<string, unknown>;
}

export interface AnalysisReport {
  tender_id: string;
  stages: StageReport[];
  duration_ms: number;
}

export interface DemoLoad {
  tender_id: string;
  title: string;
  bidders: number;
  tender_documents: number;
  historical_tenders: number;
  registered_vendors: number;
  historical_bid_records: number;
  analysis?: AnalysisReport;
}

export interface Bidder {
  vendor_id: string;
  alias: string | null;
  name: string;
  amount_cr: number | null;
  submitted_at: string | null;
}

export interface DocumentMeta {
  document_id: string;
  vendor_id: string | null;
  kind: string;
  filename: string;
  pages: number;
  sha256: string;
}

export interface Tender {
  tender_id: string;
  title: string;
  department: string | null;
  estimated_value_cr: number | null;
  published_on: string | null;
  bid_deadline: string | null;
  status: string;
  source: string;
  bidders: Bidder[];
  documents: DocumentMeta[];
  historical_tenders_available: number;
  completed_stages: string[];
}

export interface RuleSource {
  document_id: string;
  filename: string;
  page: number;
  clause: string;
}

export interface Rule {
  rule_id: string;
  category: string;
  requirement: string;
  metric: string;
  operator: string;
  threshold: unknown;
  unit: string;
  mandatory: boolean;
  applies_if: { metric: string; operator: string; threshold: unknown } | null;
  condition: string;
  clause_text: string;
  source: RuleSource;
  extraction: { method: "pattern" | "llm"; confidence: number; model: string | null };
  notes: string[];
}

export interface Rulebook {
  tender_id: string;
  method: string | null;
  model: string | null;
  warnings: string[];
  rules: Rule[];
}

export interface EvidenceRef {
  role?: string;
  document_id: string | null;
  filename: string | null;
  page: number | null;
  excerpt: string | null;
}

export interface Evaluation {
  rule_id: string;
  result: ResultStatus;
  expected: string;
  actual: unknown;
  reason: string;
  mandatory: boolean;
  evidence: EvidenceRef[];
}

export interface MatrixVendor {
  vendor_id: string;
  alias: string | null;
  name: string;
  status: VendorStatus;
  counts: Record<ResultStatus, number>;
}

export interface ComplianceMatrix {
  tender_id: string;
  rules: Pick<Rule, "rule_id" | "category" | "requirement" | "condition" | "mandatory" | "source">[];
  vendors: MatrixVendor[];
  cells: Record<string, Record<string, Evaluation>>;
  evaluations: number;
}

export interface GraphNode {
  id: string;
  type: "vendor" | "director" | "address" | "contact" | "tender" | "document";
  label: string;
  [key: string]: unknown;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  [key: string]: unknown;
}

export interface GraphView {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: { nodes: Record<string, number>; edges: Record<string, number> };
  center?: string;
}

export interface RelationshipPath {
  via: GraphNode;
  edges: string[];
}

export interface SimilarityPairSummary {
  vendors: [string, string];
  documents: [string, string];
  filenames: [string, string];
  document_similarity: number;
  high_overlap_sections: string[];
}

export interface SimilarityDetail extends SimilarityPairSummary {
  sections: {
    title: string;
    similarity: number;
    a: { document_id: string; page: number; excerpt: string };
    b: { document_id: string; page: number; excerpt: string };
  }[];
  passages: {
    section: string;
    similarity: number;
    a: { document_id: string; page: number; text: string };
    b: { document_id: string; page: number; text: string };
  }[];
  backend: string;
  baseline: { median: number | null; max: number | null };
}

export interface Similarity {
  backend: string;
  pairs: SimilarityPairSummary[];
  baseline: { median: number | null; max: number | null };
}

export interface BehaviourPair {
  vendors: [string, string];
  co_bids: number;
  expected_co_bids: number;
  jaccard: number;
  rotation_count: number;
  alternating_winners: boolean;
  price_gap_median: number | null;
  submission_gap_median_min: number | null;
  flags: Record<string, boolean>;
  anomaly: { score: number; rank: number; percentile: number; is_outlier: boolean } | null;
  current_tender: { price_gap: number; submission_gap_min: number };
}

export interface Behaviour {
  historical_tenders: number;
  model: { trained: boolean; type?: string; training_pairs?: number; outliers?: number; features?: string[] };
  pairs: BehaviourPair[];
  vendors: Record<string, { participations: number; wins: number; runner_up: number; win_rate: number }>;
}

export interface VendorRef {
  vendor_id: string;
  alias: string | null;
  name: string;
}

export interface FindingSummary {
  finding_id: string;
  category: FindingCategory;
  title: string;
  signal: string;
  level: FindingLevel;
  status: FindingStatus;
  recommendation: string;
  subject: { type: string; vendors: VendorRef[]; rule_id?: string };
  evidence_count: number;
  data_quality: string;
}

export interface EvidenceSource {
  kind: string;
  document_id?: string;
  filename?: string;
  page?: number;
  vendor_id?: string;
  field?: string;
  value?: unknown;
  tender_id?: string;
  outcomes?: Record<string, string>;
  text?: string;
  clause?: string;
  section?: string;
  similarity?: number;
  a?: { document_id: string; page: number; text: string };
  b?: { document_id: string; page: number; text: string };
  [key: string]: unknown;
}

export interface EvidenceItem {
  evidence_id: string;
  type: string;
  label: string;
  family: string;
  weight: number;
  strength: string;
  statement: string;
  metrics?: Record<string, unknown>;
  sources: EvidenceSource[];
  alternative_explanation?: string;
  recommended_verification?: string[];
}

export interface Assessment {
  support: number;
  families: string[];
  level: SignalLevel;
  evidence_count: number;
}

export interface ReasoningStep {
  step: number;
  key: string;
  label: string;
  statement: string;
  evidence_ids?: string[];
}

export interface AuditEntry {
  entry_id: number;
  tender_id: string;
  finding_id: string | null;
  action: string;
  actor: string;
  payload: Record<string, unknown>;
  created_at: string;
  prev_hash: string;
  entry_hash: string;
}

export interface Finding extends Omit<FindingSummary, "evidence_count" | "data_quality"> {
  tender_id: string;
  evidence: EvidenceItem[];
  assessment: Partial<Assessment> & Record<string, unknown>;
  reasoning: { steps: ReasoningStep[]; conclusion: string };
  data_quality: { level: string; notes: string[] };
  alternative_explanations: string[];
  recommended_verification: string[];
  disclaimer: string;
  audit: AuditEntry[];
}

export interface CounterfactualResult {
  finding_id: string;
  removed: { evidence_id: string; label: string; family: string }[];
  remaining: { evidence_id: string; label: string; family: string; weight: number }[];
  original: Assessment;
  counterfactual: Assessment;
  status: "STILL_SUPPORTED" | "DOWNGRADED" | "DISSOLVED";
  explanation: string;
  run_id?: number;
}

export interface Robustness {
  finding_id: string;
  original: Assessment;
  robustness_score: number;
  interpretation: string;
  leave_one_out: {
    evidence_id: string;
    label: string;
    family: string;
    weight: number;
    level_after: SignalLevel;
    support_after: number;
    status: string;
    critical: boolean;
  }[];
  family_ablation: { family: string; removed: string[]; level_after: SignalLevel; status: string; explanation: string }[];
  minimal_breaking_set: { size: number; evidence_ids: string[]; labels: string[] } | null;
}

export interface Snapshot {
  snapshot_id: string;
  tender_id: string;
  created_at: string;
  bundle_hash: string;
  hash_algorithm?: string;
  component_hashes?: Record<string, string>;
  documents?: number;
  findings?: number;
  dispositions?: { finding_id: string; decision: string; auditor: string }[];
  chain_payload?: ChainPayload;
  audit_head?: number;
}

export interface ChainPayload {
  case_id: string;
  tender_id: string;
  evidence_hash: string;
  audit_head_hash: string;
  timestamp: string;
  auditor_actions: string[];
}

export interface Verification {
  snapshot_id: string;
  committed_hash: string;
  current_hash: string;
  match: boolean;
  status: "INTEGRITY_VERIFIED" | "INTEGRITY_MISMATCH";
  changed_components: string[];
  changed_documents: { document_id: string; filename: string; committed_sha256: string | null; current_sha256: string | null }[];
  audit_chain: { valid: boolean; head_hash?: string; broken_at_entry?: number };
  verified_at: string;
  note: string;
}

export interface AuditLog {
  entries: AuditEntry[];
  chain: { valid: boolean; head_hash?: string; broken_at_entry?: number };
}
