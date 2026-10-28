/**
 * The backend's API contract, typed.
 *
 * These mirror the Pydantic response models. Money arrives as a decimal
 * *string* and stays a string all the way to the formatter — parsing it into
 * a JS number would quietly introduce float error into the one thing in the
 * product that must never be approximate.
 */

export const DEAL_STATES = [
  "DRAFT",
  "FUNDED",
  "DELIVERED",
  "VERIFYING",
  "RELEASED",
  "REFUNDED",
  "DISPUTED",
  "SPLIT",
] as const;

export type DealState = (typeof DEAL_STATES)[number];

export const TERMINAL_STATES: readonly DealState[] = ["RELEASED", "REFUNDED", "SPLIT"];

export type Role = "buyer" | "seller" | "reviewer";
export type DeliverableType = "url" | "file" | "image" | "repo" | "text";
export type Verdict = "pass" | "fail" | "inconclusive";
export type DecidedBy = "ai" | "human";
export type SettlementAction = "release" | "refund" | "split";
export type Actor = "buyer" | "seller" | "reviewer" | "system" | "ai" | "paypal_webhook";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
}

export interface Criterion {
  id: string;
  text: string;
  position: number;
  confirmed_by_buyer: boolean;
  confirmed_by_seller: boolean;
}

export interface Deliverable {
  id: string;
  type: DeliverableType;
  content_ref: string;
  note: string | null;
  submitted_at: string;
}

export interface CriterionFinding {
  criterion_id: string;
  text: string;
  pass: boolean;
  note: string;
}

export interface VerificationReport {
  id: string;
  verdict: Verdict;
  confidence: string;
  reasoning: string;
  per_criterion: CriterionFinding[];
  // Itemized audit view derived from per_criterion by the backend.
  verified_criteria: string[];
  unmet_or_missing_criteria: string[];
  decided_by: DecidedBy;
  recommendation: string | null;
  decided_at: string;
}

export interface VerificationResult {
  report: VerificationReport;
  state: DealState;
  released: boolean;
  policy_outcome: "auto_release" | "dispute";
  policy_reason: string;
  advisory_notice: string;
}

export interface AuditEntry {
  id: string;
  from_state: DealState | null;
  to_state: DealState;
  actor: Actor;
  event: string;
  reason: string;
  paypal_reference: string | null;
  created_at: string;
}

export interface DealSummary {
  id: string;
  title: string;
  state: DealState;
  amount: string;
  currency: string;
  created_at: string;
  updated_at: string;
}

export interface Deal {
  id: string;
  title: string;
  description: string;
  state: DealState;
  amount: string;
  currency: string;
  platform_fee: string | null;
  buyer: User;
  seller: User;
  paypal_order_id: string | null;
  paypal_capture_id: string | null;
  payout_batch_id: string | null;
  refund_id: string | null;
  created_at: string;
  updated_at: string;
  criteria: Criterion[];
  deliverables: Deliverable[];
  verification_reports: VerificationReport[];
  milestones: Milestone[];
}

export interface Milestone {
  id: string;
  position: number;
  title: string;
  description: string;
  amount: string;
  state: DealState;
  payout_batch_id: string | null;
  platform_fee: string | null;
  criteria: Criterion[];
  deliverables: Deliverable[];
  verification_reports: VerificationReport[];
}

export interface MilestoneDisputeResult {
  milestone: Milestone;
  action: SettlementAction;
  to_seller: string;
  to_buyer: string;
  platform_fee: string;
  paypal_reference: string | null;
  already_settled: boolean;
}

export interface DealWithTimeline extends Deal {
  timeline: AuditEntry[];
}

export interface CreateOrderResponse {
  paypal_order_id: string;
  approve_url: string | null;
}

export interface ClientTokenResponse {
  client_token: string;
  /** The environment-matched v6 core SDK URL (sandbox vs live). */
  sdk_url: string;
}

export interface MediationRecommendation {
  recommendation: SettlementAction;
  reasoning: string;
  suggested_seller_amount: string | null;
  advisory_notice: string;
}

export interface ResolveDisputeResponse {
  state: DealState;
  action: SettlementAction;
  to_seller: string;
  to_buyer: string;
  platform_fee: string;
  paypal_reference: string | null;
  already_settled: boolean;
}

export interface StatTile {
  key: string;
  count: number;
  amount: string;
  currency: string;
}

export interface DealSummaryWithParties extends DealSummary {
  buyer: User;
  seller: User;
}

export interface ReviewerOverview {
  held_in_escrow: StatTile;
  open_disputes: StatTile;
  released: StatTile;
  refunded: StatTile;
  deals: DealSummaryWithParties[];
}

/** The error envelope every failure uses. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    fields?: { field: string; message: string }[];
  };
}
