import type { ApiError } from "./api";

/**
 * Every query and mutation in the app fails with an ApiError, so register
 * it globally rather than annotating each hook — that way `error.code` is
 * typed at the call site without casts.
 */
declare module "@tanstack/react-query" {
  interface Register {
    defaultError: ApiError;
  }
}
