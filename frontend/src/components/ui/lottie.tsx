"use client";

import dynamic from "next/dynamic";

import { cn } from "@/lib/utils";

// Lottie touches the DOM, so it is client-only — never server-rendered.
const Lottie = dynamic(() => import("lottie-react"), { ssr: false });

interface LottieAnimationProps {
  // The imported Lottie JSON (an original animation shipped in src/animations).
  animationData: unknown;
  loop?: boolean;
  className?: string;
  ariaLabel?: string;
}

/**
 * A thin wrapper around lottie-react. Respects prefers-reduced-motion by not
 * looping (the animation settles on its final frame), so motion-sensitive
 * users get a still graphic rather than a pulsing one.
 */
export function LottieAnimation({
  animationData,
  loop = true,
  className,
  ariaLabel,
}: LottieAnimationProps) {
  const reduce =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  return (
    <div className={cn("pointer-events-none", className)} role="img" aria-label={ariaLabel}>
      <Lottie animationData={animationData} loop={reduce ? false : loop} autoplay />
    </div>
  );
}
