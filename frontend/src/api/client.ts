import type {
  AnalysisReport,
  AuditLog,
  Behaviour,
  ComplianceMatrix,
  CounterfactualResult,
  Decision,
  DemoLoad,
  DocumentVersion,
  Finding,
  FindingSummary,
  GraphView,
  Health,
  RelationshipPath,
  Robustness,
  Rulebook,
  Similarity,
  SimilarityDetail,
  Snapshot,
  ReviewDecision,
  Tender,
  Verification,
  VersionComparison,
  VersionExplanation,
  VersionHistory,
  VersionReviewResult,
  VersionVerification,
} from "./types";

export const DEMO_TENDER = "TN-2026-014";
const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/api/health"),
  loadDemo: () => post<DemoLoad>("/api/demo/load?analyze=true"),
  tamper: (documentId?: string) => post<{ document_id: string; filename: string; change: string }>(
    "/api/demo/tamper",
    { document_id: documentId ?? null },
  ),
  restore: () => post<{ restored: string[] }>("/api/demo/restore"),
  demoNewVersion: (documentId?: string) =>
    post<{ version: DocumentVersion; comparison: VersionComparison }>("/api/demo/new-version", { document_id: documentId ?? null }),

  tender: (tid: string) => request<Tender>(`/api/tenders/${tid}`),
  analyze: (tid: string) => post<AnalysisReport>(`/api/tenders/${tid}/analyze`, {}),
  rules: (tid: string) => request<Rulebook>(`/api/tenders/${tid}/rules`),
  compliance: (tid: string) => request<ComplianceMatrix>(`/api/tenders/${tid}/compliance`),
  graph: (tid: string) => request<GraphView>(`/api/tenders/${tid}/graph`),
  vendorGraph: (tid: string, vid: string, depth = 1) =>
    request<GraphView>(`/api/tenders/${tid}/graph/vendors/${vid}?depth=${depth}`),
  paths: (tid: string, a: string, b: string) =>
    request<{ paths: RelationshipPath[] }>(`/api/tenders/${tid}/graph/paths?a=${a}&b=${b}&include_tenders=true`),
  similarity: (tid: string) => request<Similarity>(`/api/tenders/${tid}/similarity`),
  similarityPair: (tid: string, a: string, b: string) =>
    request<SimilarityDetail>(`/api/tenders/${tid}/similarity/${a}/${b}`),
  behaviour: (tid: string) => request<Behaviour>(`/api/tenders/${tid}/behaviour`),

  findings: (tid: string) => request<FindingSummary[]>(`/api/tenders/${tid}/findings`),
  finding: (fid: string) => request<Finding>(`/api/findings/${fid}`),
  robustness: (fid: string) => request<Robustness>(`/api/findings/${fid}/robustness`),
  counterfactual: (fid: string, remove: string[], record = true) =>
    post<CounterfactualResult>(`/api/findings/${fid}/counterfactual`, { remove, record, actor: "auditor" }),
  disposition: (fid: string, decision: Decision, auditor: string, notes: string) =>
    post<{ status: string }>(`/api/findings/${fid}/disposition`, { decision, auditor, notes }),
  auditLog: (tid: string) => request<AuditLog>(`/api/tenders/${tid}/audit-log`),

  snapshots: (tid: string) => request<Snapshot[]>(`/api/tenders/${tid}/evidence/snapshots`),
  snapshot: (sid: string) => request<Snapshot>(`/api/evidence/snapshots/${sid}`),
  finalize: (tid: string, auditor: string, note = "") =>
    post<Snapshot>(`/api/tenders/${tid}/evidence/finalize`, { auditor, note }),
  verify: (sid: string) => request<Verification>(`/api/evidence/snapshots/${sid}/verify`),

  versions: (docId: string) => request<VersionHistory>(`/api/documents/${docId}/versions`),
  uploadVersion: async (docId: string, file: File, createdBy: string, note = "") => {
    const form = new FormData();
    form.append("file", file);
    form.append("created_by", createdBy);
    form.append("note", note);
    const res = await fetch(`${BASE}/api/documents/${docId}/versions`, { method: "POST", body: form });
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? res.statusText);
    return (await res.json()) as { version: DocumentVersion; comparison: VersionComparison };
  },
  verifyVersion: (docId: string, version: number) =>
    request<VersionVerification>(`/api/documents/${docId}/versions/${version}/verify`),
  changes: (docId: string, fromVersion: number, toVersion: number) =>
    request<VersionComparison>(`/api/documents/${docId}/changes?from_version=${fromVersion}&to_version=${toVersion}`),
  explainVersion: (docId: string, version: number) =>
    post<{ comparison: VersionComparison; explanation: VersionExplanation }>(`/api/documents/${docId}/versions/${version}/explain`, {}),
  reviewVersion: (docId: string, version: number, decision: ReviewDecision, auditor: string, notes: string) =>
    post<VersionReviewResult>(`/api/documents/${docId}/versions/${version}/review`, { decision, auditor, notes }),
  versionFileUrl: (docId: string, version: number) => `${BASE}/api/documents/${docId}/versions/${version}/file`,
  dossierUrl: (tid: string) => `${BASE}/api/tenders/${tid}/dossier-data`,
  documentUrl: (docId: string, page?: number | null) =>
    `${BASE}/api/documents/${docId}/file${page ? `#page=${page}` : ""}`,
};
