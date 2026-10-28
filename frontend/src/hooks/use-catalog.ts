"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, api } from "@/lib/api";
import type { CatalogProduct } from "@/lib/types";

export const catalogKeys = {
  search: (query: string) => ["catalog", "search", query] as const,
};

/** Product search for Shop & Escrow. Disabled until there is a query. */
export function useCatalogSearch(query: string): UseQueryResult<CatalogProduct[]> {
  return useQuery({
    queryKey: catalogKeys.search(query),
    queryFn: () => api.searchCatalog(query),
    enabled: query.trim().length > 0,
    retry: (failureCount, error: ApiError) => !error.isPermanent && failureCount < 2,
  });
}
