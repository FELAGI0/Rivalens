import type { HTMLAttributes } from "react";

/** Bordered box, no shadow, no blur. Hover shifts the border color. */
export function Card({
  className = "",
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-sm border border-line transition-colors duration-150 hover:border-fg-muted ${className}`}
      {...rest}
    />
  );
}
