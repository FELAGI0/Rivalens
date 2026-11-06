"use client";

import type { ButtonHTMLAttributes, Ref } from "react";

type Variant = "primary" | "ghost" | "danger";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  ref?: Ref<HTMLButtonElement>;
};

/** Rectangular button, radius 2px. primary/danger = accent fill, ghost = border.
 *  Animations: color-only hover (150ms) + a 2% press-down (active:scale-[0.98]). */
export function Button({
  variant = "primary",
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-sm px-4 py-2 text-sm font-medium transition-[colors,transform] duration-150 ease-out active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100";
  const styles: Record<Variant, string> = {
    primary:
      "bg-accent text-on-accent hover:bg-accent-hover border border-transparent",
    danger:
      "bg-accent text-on-accent hover:bg-accent-hover border border-transparent",
    ghost:
      "border border-line text-fg hover:border-fg-muted hover:bg-bg-subtle",
  };
  return (
    <button
      type={type}
      className={`${base} ${styles[variant]} ${className}`}
      {...rest}
    />
  );
}
