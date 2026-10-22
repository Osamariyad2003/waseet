"use client";

import { useId } from "react";

import { cn } from "@/lib/utils";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string;
  children: (props: {
    id: string;
    "aria-invalid": boolean;
    "aria-describedby": string | undefined;
  }) => React.ReactNode;
}

/**
 * Label, control, hint and error wired together.
 *
 * The error is announced (role="alert") and referenced by aria-describedby,
 * so a screen reader hears the problem rather than only seeing a red ring.
 */
export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-ink">
        {label}
      </label>
      {children({ id, "aria-invalid": Boolean(error), "aria-describedby": describedBy })}
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-status-attention">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="text-sm text-ink-faint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

const control =
  "w-full rounded-[--radius-control] border border-border-subtle bg-surface px-3.5 py-3 " +
  "text-sm text-ink transition-colors placeholder:text-ink-faint " +
  "focus:border-accent aria-[invalid=true]:border-status-attention";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(control, className)} {...props} />;
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(control, "min-h-24 resize-y", className)} {...props} />;
}

export function Select({
  className,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(control, "pe-8", className)} {...props} />;
}
