"use client";

/**
 * Server state lives here, not in components.
 *
 * One rule runs through all of it: the backend owns deal state. After any
 * action we refetch the deal rather than guessing the next state locally —
 * the state machine may have routed the deal somewhere the client would not
 * have predicted (a confident pass releases, a low-confidence pass
 * disputes), and guessing would show the user a state the server disagrees
 * with.
 */

import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, api } from "@/lib/api";
import { isInFlight } from "@/lib/status";
import type {
  AuditEntry,
  DealState,
  DealSummary,
  DealWithTimeline,
  DeliverableType,
  MediationRecommendation,
  ReviewerOverview,
  SettlementAction,
  VerificationReport,
} from "@/lib/types";

export const dealKeys = {
  all: ["deals"] as const,
  list: (state?: DealState) => ["deals", "list", state ?? "all"] as const,
  detail: (dealId: string) => ["deals", "detail", dealId] as const,
  audit: (dealId: string) => ["deals", "audit", dealId] as const,
  verification: (dealId: string) => ["deals", "verification", dealId] as const,
  recommendation: (dealId: string) => ["deals", "recommendation", dealId] as const,
  reviewerOverview: ["reviewer", "overview"] as const,
};

/** Retry transport failures, never a 4xx — a 409 means the deal moved on,
 * so retrying would just lose the same race again. */
function retryPolicy(failureCount: number, error: ApiError): boolean {
  if (error.isPermanent) return false;
  return failureCount < 2;
}

export function useDeals(state?: DealState): UseQueryResult<DealSummary[]> {
  return useQuery({
    queryKey: dealKeys.list(state),
    queryFn: () => api.listDeals(state),
    retry: retryPolicy,
  });
}

export function useDeal(dealId: string): UseQueryResult<DealWithTimeline> {
  return useQuery({
    queryKey: dealKeys.detail(dealId),
    queryFn: () => api.getDeal(dealId),
    retry: retryPolicy,
    // While the model is running, poll so the UI moves on its own instead of
    // making the user refresh. FR-12 asks for near-real-time state; polling
    // a VERIFYING deal is the honest version of that without websockets.
    refetchInterval: (query) =>
      query.state.data && isInFlight(query.state.data.state) ? 2000 : false,
  });
}

export function useAuditTrail(dealId: string): UseQueryResult<AuditEntry[]> {
  return useQuery({
    queryKey: dealKeys.audit(dealId),
    queryFn: () => api.getAudit(dealId),
    retry: retryPolicy,
  });
}

export function useVerification(
  dealId: string,
  enabled = true,
): UseQueryResult<VerificationReport> {
  return useQuery({
    queryKey: dealKeys.verification(dealId),
    queryFn: () => api.getVerification(dealId),
    enabled,
    // A 404 here means "not verified yet", which is a normal state.
    retry: (count, error) => (error.status === 404 ? false : retryPolicy(count, error)),
  });
}

export function useRecommendation(
  dealId: string,
  enabled: boolean,
): UseQueryResult<MediationRecommendation> {
  return useQuery({
    queryKey: dealKeys.recommendation(dealId),
    queryFn: () => api.getRecommendation(dealId),
    enabled,
    // The mediator call is not free; do not re-ask on every focus.
    staleTime: 5 * 60 * 1000,
    retry: retryPolicy,
  });
}

export function useReviewerOverview(): UseQueryResult<ReviewerOverview> {
  return useQuery({
    queryKey: dealKeys.reviewerOverview,
    queryFn: () => api.getReviewerOverview(),
    retry: retryPolicy,
    // The dashboard is a live operations view, so keep it fresh.
    refetchInterval: 15000,
  });
}


/** Refetch everything that describes one deal. */
function useDealInvalidator(dealId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: dealKeys.detail(dealId) }),
      queryClient.invalidateQueries({ queryKey: dealKeys.audit(dealId) }),
      queryClient.invalidateQueries({ queryKey: dealKeys.verification(dealId) }),
      queryClient.invalidateQueries({ queryKey: dealKeys.all }),
    ]);
  };
}

export function useCreateDeal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createDeal,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: dealKeys.all }),
  });
}

export function useConfirmCriteria(dealId: string) {
  const invalidate = useDealInvalidator(dealId);
  return useMutation({
    mutationFn: () => api.confirmCriteria(dealId),
    onSuccess: invalidate,
  });
}

export function useCaptureOrder(dealId: string) {
  const invalidate = useDealInvalidator(dealId);
  return useMutation({
    mutationFn: (paypalOrderId?: string) => api.captureOrder(dealId, paypalOrderId),
    onSuccess: invalidate,
  });
}

export function useSubmitDeliverable(dealId: string) {
  const invalidate = useDealInvalidator(dealId);
  return useMutation({
    mutationFn: (input: {
      type: DeliverableType;
      content_ref: string;
      note?: string | null;
    }) => api.submitDeliverable(dealId, input),
    onSuccess: invalidate,
  });
}

export function useVerify(dealId: string) {
  const invalidate = useDealInvalidator(dealId);
  return useMutation({
    mutationFn: () => api.verify(dealId),
    onSuccess: invalidate,
  });
}

export function useContest(dealId: string) {
  const invalidate = useDealInvalidator(dealId);
  return useMutation({
    mutationFn: (reason: string) => api.contest(dealId, reason),
    onSuccess: invalidate,
  });
}

export function useResolveDispute(dealId: string) {
  const invalidate = useDealInvalidator(dealId);
  return useMutation({
    mutationFn: (input: {
      action: SettlementAction;
      reasoning: string;
      seller_amount?: string | null;
    }) => api.resolveDispute(dealId, input),
    onSuccess: invalidate,
  });
}
