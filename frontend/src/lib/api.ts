/**
 * The typed API client. The only module that talks to the backend.
 *
 * Components never call `fetch`: they use the query hooks in `src/hooks`,
 * which call these functions. That keeps the network out of the render tree
 * and gives every failure the same shape.
 */

import type {
  ApiErrorBody,
  ClientTokenResponse,
  CreateOrderResponse,
  Deal,
  DealState,
  DealSummary,
  DealWithTimeline,
  Deliverable,
  DeliverableType,
  LoginResponse,
  MediationRecommendation,
  ResolveDisputeResponse,
  SettlementAction,
  User,
  VerificationReport,
  VerificationResult,
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

/** In memory, deliberately: see `src/lib/session.ts`. */
let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

export function getAuthToken(): string | null {
  return authToken;
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

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
    amount: string;
    currency: string;
  }) => request<Deal>("/deals", { method: "POST", body: input }),

  confirmCriteria: (dealId: string) =>
    request<Deal>(`/deals/${dealId}/criteria/confirm`, { method: "POST" }),

  getAudit: (dealId: string) => request<DealWithTimeline["timeline"]>(`/deals/${dealId}/audit`),

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
};
