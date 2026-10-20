"use client";

import { useTranslations } from "next-intl";

import { statusStyle } from "@/lib/status";
import type { DealState } from "@/lib/types";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  state: DealState;
  size?: "sm" | "lg";
  /** Show what the state means, for the timeline hero. */
  withMeaning?: boolean;
  className?: string;
}

/**
 * The status badge. Colour comes from the one status system, and is never
 * the only signal: the badge always carries the state's own label and a
 * glyph that survives greyscale or colour blindness.
 */
export function StatusBadge({
  state,
  size = "sm",
  withMeaning = false,
  className,
}: StatusBadgeProps) {
  const t = useTranslations();
  const style = statusStyle(state);
  const label = t(`states.${state}`);

  return (
    <span className={cn("inline-flex flex-col gap-1", className)}>
      <span
        className={cn(
          "inline-flex items-center gap-1.5 self-start rounded-full font-semibold ring-1",
          style.badge,
          size === "lg" ? "px-3.5 py-1.5 text-sm" : "px-2.5 py-1 text-xs",
        )}
      >
        <span aria-hidden className="leading-none">
          {style.glyph}
        </span>
        {label}
      </span>
      {withMeaning ? (
        <span className="text-sm text-ink-muted">{t(`stateMeaning.${state}`)}</span>
      ) : null}
    </span>
  );
}
