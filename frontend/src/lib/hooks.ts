import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, type UploadTenderInput } from "../api/client";
import { useCurrentTender, useTid } from "./tender";

export { useTid };

const noRetryOn404 = (count: number, err: unknown) =>
  !(err instanceof ApiError && (err.status === 404 || err.status === 409)) && count < 1;

export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15000, retry: false });

export const useTender = () => {
  const TID = useTid();
  return useQuery({ queryKey: ["tender", TID], queryFn: () => api.tender(TID), retry: noRetryOn404, enabled: !!TID });
};

export const useRules = () => {
  const TID = useTid();
  return useQuery({ queryKey: ["rules", TID], queryFn: () => api.rules(TID), retry: noRetryOn404, enabled: !!TID });
};

export const useCompliance = () => {
  const TID = useTid();
  return useQuery({ queryKey: ["compliance", TID], queryFn: () => api.compliance(TID), retry: noRetryOn404, enabled: !!TID });
};

export const useGraph = () => {
  const TID = useTid();
  return useQuery({ queryKey: ["graph", TID], queryFn: () => api.graph(TID), retry: noRetryOn404, enabled: !!TID });
};

export const useSimilarity = () => {
  const TID = useTid();
  return useQuery({ queryKey: ["similarity", TID], queryFn: () => api.similarity(TID), retry: noRetryOn404, enabled: !!TID });
};

export const useBehaviour = () => {
  const TID = useTid();
  return useQuery({ queryKey: ["behaviour", TID], queryFn: () => api.behaviour(TID), retry: noRetryOn404, enabled: !!TID });
};

export const useFindings = () => {
  const TID = useTid();
  return useQuery({ queryKey: ["findings", TID], queryFn: () => api.findings(TID), retry: noRetryOn404, enabled: !!TID });
};

export const useFinding = (fid: string) =>
  useQuery({ queryKey: ["finding", fid], queryFn: () => api.finding(fid), retry: noRetryOn404, enabled: !!fid });

export const useAuditLog = () => {
  const TID = useTid();
  return useQuery({ queryKey: ["audit", TID], queryFn: () => api.auditLog(TID), retry: noRetryOn404, enabled: !!TID });
};

export const useSnapshots = () => {
  const TID = useTid();
  return useQuery({ queryKey: ["snapshots", TID], queryFn: () => api.snapshots(TID), retry: noRetryOn404, enabled: !!TID });
};

export const useTenders = () => useQuery({ queryKey: ["tenders"], queryFn: api.tenders });

/** Uploads a real tender PDF, extracts its rulebook and makes it the current tender. */
export function useUploadTender() {
  const qc = useQueryClient();
  const { setTid } = useCurrentTender();
  return useMutation({
    mutationFn: (input: UploadTenderInput) => api.uploadTender(input),
    onSuccess: (created) => {
      setTid(created.tender_id);
      return qc.invalidateQueries();
    },
  });
}

export const isNotLoaded = (err: unknown) => err instanceof ApiError && (err.status === 404 || err.status === 409);

export function useRunAnalysis() {
  const qc = useQueryClient();
  const TID = useTid();
  return useMutation({
    mutationFn: () => api.analyze(TID),
    onSuccess: (report) => {
      qc.setQueryData(["analysis", TID], report);
      return qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "analysis" });
    },
  });
}

export const useAnalysisReport = () => {
  const TID = useTid();
  return useQuery<import("../api/types").AnalysisReport | null>({
    queryKey: ["analysis", TID],
    queryFn: () => null,
    staleTime: Infinity,
  });
};
