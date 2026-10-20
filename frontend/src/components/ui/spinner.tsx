import { cn } from "@/lib/utils";

/** A busy indicator that announces itself rather than only spinning. */
export function Spinner({ className, label }: { className?: string; label: string }) {
  return (
    <span role="status" aria-live="polite" className="inline-flex items-center gap-2">
      <span
        aria-hidden
        className={cn(
          "size-4 animate-spin rounded-full border-2 border-current border-t-transparent",
          className,
        )}
      />
      <span className="sr-only">{label}</span>
    </span>
  );
}
