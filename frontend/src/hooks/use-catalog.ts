"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, api } from "@/lib/api";
import type { CatalogProduct, PriceHistoryData, ProductDetail } from "@/lib/types";

export const catalogKeys = {
  search: (query: string) => ["catalog", "search", query] as const,
  product: (id: string) => ["catalog", "product", id] as const,
  similar: (id: string) => ["catalog", "similar", id] as const,
  priceHistory: (id: string) => ["catalog", "price-history", id] as const,
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

/** Full product details (all offers, images, metadata). */
export function useProduct(productId: string): UseQueryResult<ProductDetail> {
  return useQuery({
    queryKey: catalogKeys.product(productId),
    queryFn: () => api.getProduct(productId),
    enabled: productId.length > 0,
    retry: (failureCount, error: ApiError) => !error.isPermanent && failureCount < 2,
  });
}

/** Similar products for the "You might also like" section. */
export function useSimilarProducts(productId: string): UseQueryResult<CatalogProduct[]> {
  return useQuery({
    queryKey: catalogKeys.similar(productId),
    queryFn: () => api.getSimilarProducts(productId),
    enabled: productId.length > 0,
    retry: (failureCount, error: ApiError) => !error.isPermanent && failureCount < 2,
  });
}

/** Price history with statistics for a product. */
export function usePriceHistory(productId: string): UseQueryResult<PriceHistoryData> {
  return useQuery({
    queryKey: catalogKeys.priceHistory(productId),
    queryFn: () => api.getPriceHistory(productId),
    enabled: productId.length > 0,
    retry: (failureCount, error: ApiError) => !error.isPermanent && failureCount < 2,
  });
}
