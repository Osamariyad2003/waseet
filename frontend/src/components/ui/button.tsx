"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef } from "react";

import { cn } from "@/lib/utils";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-[--radius-control] font-medium " +
    "transition-all duration-150 " +
    "disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-accent text-white shadow-sm hover:bg-accent-hover hover:shadow-md active:shadow-sm",
        secondary: "bg-surface text-ink ring-1 ring-border-subtle hover:bg-surface-muted hover:ring-ink-faint/30",
        ghost: "text-ink-muted hover:bg-surface-muted hover:text-ink",
        danger:
          "bg-status-attention text-white shadow-sm hover:brightness-95 hover:shadow-md",
        success: "bg-status-paid text-white shadow-sm hover:brightness-95 hover:shadow-md",
      },
      size: {
        sm: "h-9 px-3 text-sm",
        md: "h-11 px-5 text-sm",
        lg: "h-12 px-6 text-base",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof button> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(button({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";
