import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, DEMO_TENDER } from "../api/client";

export const TID = DEMO_TENDER;

const noRetryOn404 = (count: number, err: unknown) =>
  !(err instanceof ApiError && (err.status === 404 || err.status === 409)) && count < 1;

export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15000, retry: false });

export const useTender = () => useQuery({ queryKey: ["tender", TID], queryFn: () => api.tender(TID), retry: noRetryOn404 });

export const useRules = () => useQuery({ queryKey: ["rules", TID], queryFn: () => api.rules(TID), retry: noRetryOn404 });

export const useCompliance = () =>
  useQuery({ queryKey: ["compliance", TID], queryFn: () => api.compliance(TID), retry: noRetryOn404 });

export const useGraph = () => useQuery({ queryKey: ["graph", TID], queryFn: () => api.graph(TID), retry: noRetryOn404 });

export const useSimilarity = () =>
  useQuery({ queryKey: ["similarity", TID], queryFn: () => api.similarity(TID), retry: noRetryOn404 });

export const useBehaviour = () =>
  useQuery({ queryKey: ["behaviour", TID], queryFn: () => api.behaviour(TID), retry: noRetryOn404 });

export const useFindings = () =>
  useQuery({ queryKey: ["findings", TID], queryFn: () => api.findings(TID), retry: noRetryOn404 });

export const useFinding = (fid: string) =>
  useQuery({ queryKey: ["finding", fid], queryFn: () => api.finding(fid), retry: noRetryOn404, enabled: !!fid });

export const useAuditLog = () => useQuery({ queryKey: ["audit", TID], queryFn: () => api.auditLog(TID), retry: noRetryOn404 });

export const useSnapshots = () =>
  useQuery({ queryKey: ["snapshots", TID], queryFn: () => api.snapshots(TID), retry: noRetryOn404 });

/** Reloads the demo dataset + analysis and refreshes every cached view. */
export function useLoadDemo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.loadDemo,
    onSuccess: (result) => {
      if (result.analysis) qc.setQueryData(["analysis", TID], result.analysis);
      return qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "analysis" });
    },
  });
}

export const isNotLoaded = (err: unknown) => err instanceof ApiError && (err.status === 404 || err.status === 409);

export function useRunAnalysis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.analyze(TID),
    onSuccess: (report) => {
      qc.setQueryData(["analysis", TID], report);
      return qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "analysis" });
    },
  });
}

export const useAnalysisReport = () =>
  useQuery<import("../api/types").AnalysisReport | null>({
    queryKey: ["analysis", TID],
    queryFn: () => null,
    staleTime: Infinity,
  });
