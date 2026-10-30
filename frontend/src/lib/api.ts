/**
 * The typed API client. The only module that talks to the backend.
 *
 * Components never call `fetch`: they use the query hooks in `src/hooks`,
 * which call these functions. That keeps the network out of the render tree
 * and gives every failure the same shape.
 */

import type {
  AccountProfile,
  ActivityEntry,
  ApiErrorBody,
  CatalogProduct,
  Certificate,
  PriceHistoryData,
  ProductDetail,
  ClientTokenResponse,
  DealTerms,
  CreateOrderResponse,
  Deal,
  DealState,
  DealSummary,
  DealWithTimeline,
  Deliverable,
  DeliverableType,
  ExploreResponse,
  HomeSummary,
  LoginResponse,
  MediationRecommendation,
  MilestoneVerificationResult,
  Offer,
  PayoutView,
  ResolveDisputeResponse,
  SettlementAction,
  User,
  VerificationReport,
  VerificationResult,
  WalletOverview,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** A failure with the backend's own error code, so the UI can react to the
 * cause rather than pattern-matching on prose. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields?: { field: string; message: string }[];

  constructor(
    status: number,
    code: string,
    message: string,
    fields?: { field: string; message: string }[],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }

  /** Retrying is pointless for these — the request itself is the problem. */
  get isPermanent(): boolean {
    return this.status < 500 && this.status !== 408 && this.status !== 429;
  }

  get isAuthFailure(): boolean {
    return this.status === 401;
  }

  /** A conflict with the deal's real state: refetch rather than retry. */
  get isStateConflict(): boolean {
    return this.status === 409;
  }
}

/** Where a restored session is mirrored. See `hooks/use-session.tsx`. */
export const TOKEN_STORAGE_KEY = "waseet.token";

let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
  tokenCleared = token === null;
}

/** True once the app has deliberately signed out, so a stale mirrored token
 * is not resurrected from storage on the next request. */
let tokenCleared = false;

/**
 * The bearer token for the next request.
 *
 * Falls back to the mirrored copy in sessionStorage, because on a fresh page
 * load a component's first query can fire before the session provider's
 * effect has installed the in-memory token — which would show an
 * authentication error to someone who is perfectly well signed in.
 */
export function getAuthToken(): string | null {
  if (authToken) return authToken;
  if (tokenCleared || typeof window === "undefined") return null;
  try {
    authToken = window.sessionStorage.getItem(TOKEN_STORAGE_KEY);
    return authToken;
  } catch {
    return null;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    // The backend is unreachable. Surfaced as a 0 so the UI can tell this
    // apart from a server that answered with an error.
    throw new ApiError(0, "network_error", "Could not reach the Waseet server.");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload: unknown = text ? safeParse(text) : null;

  if (!response.ok) {
    const envelope = payload as ApiErrorBody | null;
    throw new ApiError(
      response.status,
      envelope?.error?.code ?? "unexpected_error",
      envelope?.error?.message ?? "Something went wrong.",
      envelope?.error?.fields,
    );
  }

  return payload as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export const api = {
  // --- auth ---------------------------------------------------------------
  login: (email: string, password: string) =>
    request<LoginResponse>("/auth/login", { method: "POST", body: { email, password } }),

  me: () => request<User>("/auth/me"),

  // --- deals --------------------------------------------------------------
  listDeals: (state?: DealState) =>
    request<DealSummary[]>(`/deals${state ? `?state=${state}` : ""}`),

  getDeal: (dealId: string) => request<DealWithTimeline>(`/deals/${dealId}`),

  createDeal: (input: {
    seller_email: string;
    title: string;
    description: string;
    amount?: string;
    currency: string;
    milestones?: { title: string; description: string; amount: string }[];
  }) => request<Deal>("/deals", { method: "POST", body: input }),

  confirmCriteria: (dealId: string) =>
    request<Deal>(`/deals/${dealId}/criteria/confirm`, { method: "POST" }),

  getAudit: (dealId: string) => request<DealWithTimeline["timeline"]>(`/deals/${dealId}/audit`),

  getTerms: (dealId: string) => request<DealTerms>(`/deals/${dealId}/terms`),

  getPayouts: (dealId: string) => request<PayoutView[]>(`/deals/${dealId}/payouts`),

  getPaypalActivity: (dealId: string) =>
    request<ActivityEntry[]>(`/deals/${dealId}/paypal-activity`),

  // --- funding ------------------------------------------------------------
  getClientToken: () => request<ClientTokenResponse>("/paypal/client-token"),

  createOrder: (dealId: string) =>
    request<CreateOrderResponse>(`/deals/${dealId}/order`, { method: "POST" }),

  captureOrder: (dealId: string, paypalOrderId?: string) =>
    request<Deal>(`/deals/${dealId}/capture`, {
      method: "POST",
      body: { paypal_order_id: paypalOrderId ?? null },
    }),

  // --- deliverable & verification ----------------------------------------
  submitDeliverable: (
    dealId: string,
    input: { type: DeliverableType; content_ref: string; note?: string | null },
  ) => request<Deliverable>(`/deals/${dealId}/deliverable`, { method: "POST", body: input }),

  verify: (dealId: string) =>
    request<VerificationResult>(`/deals/${dealId}/verify`, { method: "POST" }),

  // --- milestones ---------------------------------------------------------
  submitMilestoneDeliverable: (
    dealId: string,
    milestoneId: string,
    input: { type: DeliverableType; content_ref: string; note?: string | null },
  ) =>
    request<Deliverable>(`/deals/${dealId}/milestones/${milestoneId}/deliverable`, {
      method: "POST",
      body: input,
    }),

  verifyMilestone: (dealId: string, milestoneId: string) =>
    request<MilestoneVerificationResult>(`/deals/${dealId}/milestones/${milestoneId}/verify`, {
      method: "POST",
    }),

  getVerification: (dealId: string) =>
    request<VerificationReport>(`/deals/${dealId}/verification`),

  contest: (dealId: string, reason: string) =>
    request<Deal>(`/deals/${dealId}/contest`, { method: "POST", body: { reason } }),

  // --- disputes -----------------------------------------------------------
  getRecommendation: (dealId: string) =>
    request<MediationRecommendation>(`/deals/${dealId}/dispute/recommendation`),

    resolveDispute: (
    dealId: string,
    input: { action: SettlementAction; reasoning: string; seller_amount?: string | null },
  ) =>
    request<ResolveDisputeResponse>(`/deals/${dealId}/dispute/resolve`, {
      method: "POST",
      body: {
        action: input.action,
        reasoning: input.reasoning,
        seller_amount: input.seller_amount ?? null,
      },
    }),

  // --- wallet / explore / account / home -----------------------------------
  getWalletOverview: () => request<WalletOverview>("/wallet/overview"),

  getExplore: () => request<ExploreResponse>("/explore"),

  getAccountProfile: () => request<AccountProfile>("/account/profile"),

  updateAccountProfile: (input: { full_name?: string; paypal_account_ref?: string }) =>
    request<AccountProfile>("/account/profile", { method: "PATCH", body: input }),

  getHomeSummary: () => request<HomeSummary>("/home/summary"),

  // --- marketplace --------------------------------------------------------
  // --- public proof-of-escrow certificate --------------------------------
  getCertificate: (dealId: string) => request<Certificate>(`/verify/${dealId}`),

  // --- product catalog (Shop & Escrow) -----------------------------------
  searchCatalog: (query: string, limit = 12) =>
    request<CatalogProduct[]>(
      `/catalog/search?q=${encodeURIComponent(query)}&limit=${limit}`,
    ),

  getProduct: (productId: string) =>
    request<ProductDetail>(`/catalog/products/${encodeURIComponent(productId)}`),

  getSimilarProducts: (productId: string, limit = 6) =>
    request<CatalogProduct[]>(
      `/catalog/products/${encodeURIComponent(productId)}/similar?limit=${limit}`,
    ),

  getPriceHistory: (productId: string, days = 90) =>
    request<PriceHistoryData>(
      `/catalog/products/${encodeURIComponent(productId)}/price-history?days=${days}`,
    ),

  listOffers: () => request<Offer[]>("/offers"),

  getMyOffers: () => request<Offer[]>("/offers/mine"),

  createOffer: (input: {
    title: string;
    description: string;
    category: string;
    amount: string;
    currency: string;
  }) => request<Offer>("/offers", { method: "POST", body: input }),

  delistOffer: (offerId: string) =>
    request<void>(`/offers/${offerId}`, { method: "DELETE" }),
};
