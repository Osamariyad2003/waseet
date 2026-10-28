"use client";

import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, api } from "@/lib/api";
import type { Offer } from "@/lib/types";

export const offerKeys = {
  all: ["offers"] as const,
  list: ["offers", "list"] as const,
  mine: ["offers", "mine"] as const,
};

function retryPolicy(failureCount: number, error: ApiError): boolean {
  if (error.isPermanent) return false;
  return failureCount < 2;
}

export function useOffers(): UseQueryResult<Offer[]> {
  return useQuery({ queryKey: offerKeys.list, queryFn: api.listOffers, retry: retryPolicy });
}

export function useMyOffers(enabled = true): UseQueryResult<Offer[]> {
  return useQuery({
    queryKey: offerKeys.mine,
    queryFn: api.getMyOffers,
    enabled,
    retry: retryPolicy,
  });
}

export function useCreateOffer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createOffer,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: offerKeys.all }),
  });
}

export function useDelistOffer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (offerId: string) => api.delistOffer(offerId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: offerKeys.all }),
  });
}
